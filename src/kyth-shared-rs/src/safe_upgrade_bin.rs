use std::io::Read;
use std::os::unix::process::CommandExt;
use std::process::Stdio;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const REQUIRED_FREE_BYTES: u64 = 2 * 1024 * 1024 * 1024;
const BOOT_FREE_MIN_BYTES: u64 = 500 * 1024 * 1024;
const VAR_CACHE_FREE_MIN_BYTES: u64 = 500 * 1024 * 1024;
const TERM_GRACE: Duration = Duration::from_secs(10);
const BOOTC_TIMEOUT: Duration = Duration::from_secs(3600);
const DEFAULT_CONFIG: &str = "/etc/kyth/auto-update.toml";

/// Set by the SIGTERM watcher thread. When true, the in-flight `bootc`
/// child has been (or is being) torn down and no staged state may be
/// recorded: a terminated upgrade must never look staged.
static CANCELLED: AtomicBool = AtomicBool::new(false);

fn now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64
}

fn rollout_ring(last_known: &str) -> Result<String, String> {
    // Strict: an explicitly configured unknown ring is a hard error and the
    // stored state keeps the last known ring (staging never runs).
    kyth_shared::system::safe_upgrade_policy::load_rollout_ring(DEFAULT_CONFIG, last_known)
}

fn free_bytes(path: &str) -> Option<u64> {
    let stat = rustix::fs::statvfs(path).ok()?;
    Some(stat.f_bavail.saturating_mul(stat.f_frsize))
}

fn check_free(path: &str, min: u64) -> Result<(), String> {
    if let Some(free) = free_bytes(path) {
        if free < min {
            return Err(format!(
                "Not enough free disk space on {path}: {} MiB free, need {} MiB",
                free / (1024 * 1024),
                min / (1024 * 1024)
            ));
        }
    }
    Ok(())
}

/// Best-effort removal of dracut scratch left under `/var/tmp` when an
/// upgrade fails or is terminated. dracut runs with `--tmpdir /var/tmp`;
/// an interrupted build can leave multi-hundred-MB stage directories behind.
fn scrub_dracut_scratch() {
    let Ok(entries) = std::fs::read_dir("/var/tmp") else {
        return;
    };
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        if !(name.starts_with("dracut.") || name.starts_with(".dracut")) {
            continue;
        }
        let path = entry.path();
        if path.is_dir() {
            let _ = std::fs::remove_dir_all(&path);
        } else {
            let _ = std::fs::remove_file(&path);
        }
    }
}

fn output_text(output: &std::process::Output) -> String {
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    kyth_shared::system::process::redact_sensitive_text(
        kyth_shared::system::process::strip_ansi(text.trim()).as_str(),
    )
    .chars()
    .take(2000)
    .collect()
}

/// Watch for SIGTERM on a dedicated thread: libc-level `sigwait` needs no
/// extra crate. The mask is installed before the upgrade child spawns so the
/// watcher thread — not the default disposition — owns delivery.
fn arm_sigterm_forwarder() {
    unsafe {
        let mut set: libc::sigset_t = std::mem::zeroed();
        libc::sigemptyset(&mut set);
        libc::sigaddset(&mut set, libc::SIGTERM);
        libc::pthread_sigmask(libc::SIG_BLOCK, &set, std::ptr::null_mut());
    }
    std::thread::spawn(|| unsafe {
        let mut set: libc::sigset_t = std::mem::zeroed();
        libc::sigemptyset(&mut set);
        libc::sigaddset(&mut set, libc::SIGTERM);
        let mut signo = 0;
        if libc::sigwait(&set, &mut signo) == 0 && signo == libc::SIGTERM {
            CANCELLED.store(true, Ordering::SeqCst);
        }
    });
}

const MAX_CAPTURE_BYTES: usize = 1024 * 1024;

fn drain_pipe(pipe: &mut Option<impl Read + Send + 'static>) -> Vec<u8> {
    let mut buf = Vec::new();
    if let Some(pipe) = pipe.as_mut() {
        let mut chunk = [0u8; 8192];
        let mut truncated = false;
        loop {
            let count = match pipe.read(&mut chunk) {
                Ok(0) | Err(_) => break,
                Ok(count) => count,
            };
            let room = MAX_CAPTURE_BYTES.saturating_sub(buf.len());
            let copied = count.min(room);
            buf.extend_from_slice(&chunk[..copied]);
            truncated |= copied < count;
        }
        if truncated {
            buf.extend_from_slice(b"\n...[truncated]");
        }
    }
    buf
}

/// Read a bounded stderr fragment, returning on either progress delimiter.
/// `bootc` uses carriage returns for terminal progress bars, so waiting only
/// for `\n` can hide all updates until the next log line or process exit.
fn read_progress_fragment(
    reader: &mut impl std::io::BufRead,
    fragment: &mut Vec<u8>,
    limit: usize,
) -> std::io::Result<Option<bool>> {
    fragment.clear();
    let mut truncated = false;
    loop {
        let available = reader.fill_buf()?;
        if available.is_empty() {
            return Ok(if fragment.is_empty() && !truncated {
                None
            } else {
                Some(truncated)
            });
        }
        let delimiter = available
            .iter()
            .position(|byte| matches!(byte, b'\n' | b'\r'));
        let consumed = delimiter.map_or(available.len(), |index| index + 1);
        let room = limit.saturating_sub(fragment.len());
        let copied = consumed.min(room);
        fragment.extend_from_slice(&available[..copied]);
        truncated |= copied < consumed;
        let ended = delimiter.is_some();
        reader.consume(consumed);
        if ended {
            return Ok(Some(truncated));
        }
        if fragment.len() == limit {
            // Keep draining an oversized record to its delimiter without
            // retaining more bytes or interpreting a truncated marker.
            truncated = true;
        }
    }
}

/// Drain bootc's stderr while translating progress fragments into
/// `KYTH_STAGE_PROGRESS` marker lines on our stdout, where the Hub streams
/// them into the Updates page. The full stderr is still returned for the
/// terminal job detail on failure.
fn drain_stderr_with_progress(pipe: &mut Option<impl Read + Send + 'static>) -> Vec<u8> {
    let mut collected = Vec::new();
    let Some(pipe) = pipe.as_mut() else {
        return collected;
    };
    let mut reader = std::io::BufReader::new(pipe);
    let mut chunk = Vec::new();
    let mut progress = StageProgress::default();
    let mut capture_truncated = false;
    loop {
        let truncated = match read_progress_fragment(&mut reader, &mut chunk, 64 * 1024) {
            Ok(Some(truncated)) => truncated,
            Ok(None) | Err(_) => break,
        };
        let room = MAX_CAPTURE_BYTES.saturating_sub(collected.len());
        let copied = chunk.len().min(room);
        collected.extend_from_slice(&chunk[..copied]);
        capture_truncated |= copied < chunk.len();
        if !truncated {
            let text = String::from_utf8_lossy(&chunk);
            let fragment = text.trim_matches(['\n', '\r']);
            if let Some(marker) = classify_bootc_fragment(fragment, &mut progress) {
                println!("{marker}");
                let _ = std::io::Write::flush(&mut std::io::stdout());
            }
        }
    }
    if capture_truncated {
        collected.extend_from_slice(b"\n...[truncated]");
    }
    collected
}

/// Live staging progress parsed from `bootc upgrade` stderr.
///
/// Download reserves 0–85, deploy 85–99 (100 is only reported on clean
/// exit, so a killed or failed stage can never display complete).
#[derive(Debug, Default)]
struct StageProgress {
    blobs_needed: u64,
    blobs_started: std::collections::HashSet<String>,
    blobs_done: u64,
    blob_totals: std::collections::HashMap<String, u64>,
    blob_current: std::collections::HashMap<String, u64>,
    fetch_finalized: bool,
    deploy_steps: u64,
    last_pct: u8,
    last_detail: String,
    last_emit: Option<std::time::Instant>,
}

impl StageProgress {
    fn downloaded_bytes(&self) -> u64 {
        self.blob_current
            .iter()
            .map(|(id, current)| (*current).min(*self.blob_totals.get(id).unwrap_or(&u64::MAX)))
            .sum()
    }

    fn total_bytes(&self) -> u64 {
        self.blob_totals.values().sum()
    }

    fn pct(&self) -> (u8, &'static str) {
        if self.deploy_steps > 0 || self.fetch_finalized {
            // Deploy is a short discrete tail: step the last stretch so the
            // bar keeps moving while dracut and the bootloader run.
            let step_pct = 85u8
                .saturating_add((self.deploy_steps.min(7) * 2) as u8)
                .min(99);
            let phase = if self.deploy_steps > 0 {
                "install"
            } else {
                "download"
            };
            return (step_pct.max(85), phase);
        }
        if self.blobs_needed > 0 {
            let frac = (self.blobs_done as f64 + 0.5 * self.blobs_started.len() as f64)
                / self.blobs_needed as f64;
            return ((85.0 * frac.clamp(0.0, 1.0)) as u8, "download");
        }
        let (downloaded, total) = (self.downloaded_bytes(), self.total_bytes());
        if total > 0 {
            return ((85.0 * downloaded as f64 / total as f64) as u8, "download");
        }
        (0, "download")
    }
}

fn parse_byte_size(value: f64, unit: &str) -> u64 {
    let factor = match unit.to_ascii_lowercase().as_str() {
        "kib" | "kb" => 1024.0,
        "mib" | "mb" => 1024.0 * 1024.0,
        "gib" | "gb" => 1024.0 * 1024.0 * 1024.0,
        "tib" | "tb" => 1024.0 * 1024.0 * 1024.0 * 1024.0,
        _ => 1.0,
    };
    (value * factor) as u64
}

const DEPLOY_KEYWORDS: &[&str] = &[
    "merging layer",
    "writing commit",
    "deploying",
    "staged deployment",
    "dracut",
    "bootloader",
    "staged update",
];

/// File descriptor handed to `bootc upgrade --progress-fd`. Any value above
/// stderr works; bootc rejects 0..=2.
const BOOTC_PROGRESS_FD: libc::c_int = 3;

/// State for bootc's machine-readable progress stream (`--progress-fd`).
///
/// With stderr piped, bootc's indicatif bars are hidden, so the stderr
/// parser above sees no byte counts at all and the Hub bar sat at the initial
/// 1% for the whole download. The JSON stream carries the real numbers.
#[derive(Debug, Default)]
struct JsonProgress {
    last_pct: u8,
    last_detail: String,
}

/// Download is allotted the first 85% of the bar; importing/deploying the rest
/// (same split as the stderr parser, so the two streams never fight).
const DOWNLOAD_SHARE_PCT: f64 = 85.0;

fn mib(bytes: u64) -> f64 {
    bytes as f64 / 1024.0 / 1024.0
}

/// Translate one bootc progress JSON line into a `KYTH_STAGE_PROGRESS` marker.
/// Returns `None` for unknown/garbled lines and for updates that would not
/// change what the Hub shows. Never moves the percentage backwards.
fn classify_progress_json(line: &str, state: &mut JsonProgress) -> Option<String> {
    let event: serde_json::Value = serde_json::from_str(line.trim()).ok()?;
    let kind = event.get("type")?.as_str()?;
    let task = event
        .get("task")
        .and_then(|value| value.as_str())
        .unwrap_or("");
    let num = |key: &str| event.get(key).and_then(|value| value.as_u64()).unwrap_or(0);

    let (pct, phase, detail) = match (kind, task) {
        ("ProgressBytes", "pulling") => {
            let (bytes, total) = (num("bytes"), num("bytesTotal"));
            let (steps, steps_total) = (num("steps"), num("stepsTotal"));
            let fraction = if total > 0 {
                bytes as f64 / total as f64
            } else if steps_total > 0 {
                steps as f64 / steps_total as f64
            } else {
                0.0
            };
            // Never show 0% (the stage already announced 1%) or more than the
            // download share: the rest belongs to import and deploy.
            let pct = ((DOWNLOAD_SHARE_PCT * fraction.clamp(0.0, 1.0)) as u8).max(1);
            let layer = (steps + 1).min(steps_total.max(1));
            let detail = if total > 0 {
                format!(
                    "Downloading layer {layer} of {} · {:.0} MiB of {:.0} MiB",
                    steps_total.max(1),
                    mib(bytes.min(total)),
                    mib(total)
                )
            } else if steps_total > 0 {
                format!("Downloading layer {layer} of {steps_total}")
            } else {
                "Downloading the update".to_string()
            };
            (pct, "download", detail)
        }
        // A retried pull announces itself here; keep the bar where it was.
        ("ProgressSteps", "pulling") => {
            let description = event.get("description").and_then(|value| value.as_str())?;
            (state.last_pct.max(1), "download", description.to_string())
        }
        ("ProgressSteps", "importing") => {
            if num("steps") >= num("stepsTotal").max(1) {
                (88, "install", "Image downloaded, staging it".to_string())
            } else {
                (86, "install", "Importing the image".to_string())
            }
        }
        _ => return None,
    };

    if pct < state.last_pct {
        return None;
    }
    if pct == state.last_pct && detail == state.last_detail {
        return None;
    }
    state.last_pct = pct;
    state.last_detail = detail.clone();
    Some(format!(
        "KYTH_STAGE_PROGRESS pct={pct} phase={phase} detail={detail}"
    ))
}

/// Read bootc's JSON progress lines from the pipe and forward them to the Hub
/// as marker lines. Ends at EOF (child exit).
fn drain_json_progress(pipe: std::fs::File) {
    let mut reader = std::io::BufReader::new(pipe);
    let mut line = Vec::new();
    let mut state = JsonProgress::default();
    loop {
        match read_progress_fragment(&mut reader, &mut line, 256 * 1024) {
            Ok(Some(false)) => {}
            // Oversized record: skipped, never interpreted.
            Ok(Some(true)) => continue,
            Ok(None) | Err(_) => break,
        }
        let text = String::from_utf8_lossy(&line);
        if let Some(marker) = classify_progress_json(&text, &mut state) {
            println!("{marker}");
            let _ = std::io::Write::flush(&mut std::io::stdout());
        }
    }
}

/// Classify one stderr fragment (split on both `\n` and `\r`, ANSI
/// stripped). Returns a marker line when progress visibly moved.
fn classify_bootc_fragment(fragment: &str, state: &mut StageProgress) -> Option<String> {
    let clean = kyth_shared::system::process::strip_ansi(fragment);
    let line = clean.trim();
    if line.is_empty() {
        return None;
    }
    let lower = line.to_lowercase();

    // Totals: "layers already present: 30; layers needed: 39 (4.4 GB)".
    if let Some(idx) = lower.find("layers needed:") {
        let rest = &lower[idx + "layers needed:".len()..];
        if let Some(count) = rest.split_whitespace().next().and_then(|token| {
            token
                .trim_matches(|c: char| !c.is_ascii_digit())
                .parse::<u64>()
                .ok()
        }) {
            if count > 0 {
                state.blobs_needed = count;
            }
        }
    }

    // Per-blob byte progress from indicatif bars:
    // "a1b2c3d4e5f6 [===>...] 123MiB / 500MiB (10MiB/s)".
    if let Some(prefix) = line
        .split_whitespace()
        .next()
        .filter(|token| token.len() == 12 && token.chars().all(|c| c.is_ascii_hexdigit()))
    {
        if let Some(slash) = line.find('/') {
            let left_trim = line[..slash].trim_end();
            let left_unit: String = left_trim
                .chars()
                .rev()
                .take_while(|c| c.is_ascii_alphabetic())
                .collect::<String>()
                .chars()
                .rev()
                .collect();
            let num_part = &left_trim[..left_trim.len().saturating_sub(left_unit.len())];
            let left_num: String = num_part
                .chars()
                .rev()
                .take_while(|c| c.is_ascii_digit() || *c == '.')
                .collect::<String>()
                .chars()
                .rev()
                .collect();
            let right_token = line[slash + 1..].split_whitespace().next().unwrap_or("");
            let right_num: String = right_token
                .chars()
                .take_while(|c| c.is_ascii_digit() || *c == '.')
                .collect();
            let right_unit: String = right_token
                .chars()
                .skip_while(|c| c.is_ascii_digit() || *c == '.')
                .take_while(|c| c.is_ascii_alphabetic())
                .collect();
            if let (Ok(value), Ok(total)) = (left_num.parse::<f64>(), right_num.parse::<f64>()) {
                if !left_unit.is_empty() && !right_unit.is_empty() && total > 0.0 {
                    let id = prefix.to_string();
                    state.blobs_started.insert(id.clone());
                    state
                        .blob_totals
                        .insert(id.clone(), parse_byte_size(total, &right_unit).max(1));
                    // Downloaded bytes never move backwards: indicatif
                    // re-renders an earlier blob while a later one completes.
                    let current = parse_byte_size(value, &left_unit);
                    state
                        .blob_current
                        .entry(id)
                        .and_modify(|known| *known = (*known).max(current))
                        .or_insert(current);
                }
            }
        }
    }

    // Blob start lines ("Copying blob sha256:…") count in-flight work when
    // no byte bars are visible (piped skopeo-style output is start-only).
    if lower.starts_with("copying blob") || lower.starts_with("copying config") {
        let done =
            lower.contains("done") || lower.contains("already exists") || lower.contains("skipped");
        match line.split_whitespace().nth(2) {
            Some(digest) if digest.len() >= 7 => {
                let id: String = digest.chars().take(12).collect();
                if done {
                    state.blobs_done += 1;
                    state.blobs_started.remove(&id);
                    state.blob_current.remove(&id);
                } else {
                    state.blobs_started.insert(id);
                }
            }
            _ => {
                if done {
                    state.blobs_done += 1;
                } else {
                    state
                        .blobs_started
                        .insert(format!("blob-{}", state.blobs_started.len()));
                }
            }
        }
    }

    // Fetch tail: manifest stored, image fully pulled, deploy about to run.
    if lower.contains("writing manifest")
        || lower.contains("storing signatures")
        || lower.contains("already have manifest")
    {
        state.fetch_finalized = true;
    }

    // Deploy phase: discrete steps after the pull.
    if DEPLOY_KEYWORDS
        .iter()
        .any(|keyword| lower.contains(keyword))
    {
        state.deploy_steps += 1;
    }

    let (pct, phase) = state.pct();
    // Monotonic: a re-rendered bar for an earlier blob must not move the
    // bar backwards past a completed sibling.
    if pct < state.last_pct && !(phase == "install" && state.last_pct < 85) {
        return None;
    }
    let detail = if phase == "install" {
        "Installing the staged image".to_string()
    } else if state.blobs_needed > 0 && state.total_bytes() > 0 {
        let done = state.blobs_done.min(state.blobs_needed);
        let (downloaded, total) = (state.downloaded_bytes(), state.total_bytes());
        format!(
            "Downloading layer {} of {} · {:.0} MiB of {:.0} MiB",
            done + 1,
            state.blobs_needed,
            downloaded as f64 / 1024.0 / 1024.0,
            total as f64 / 1024.0 / 1024.0
        )
    } else if state.blobs_needed > 0 {
        let done = state.blobs_done.min(state.blobs_needed);
        format!("Downloading layer {} of {}", done + 1, state.blobs_needed)
    } else {
        let (downloaded, total) = (state.downloaded_bytes(), state.total_bytes());
        if total > 0 {
            format!(
                "Downloading {:.1} of {:.1} GB",
                downloaded as f64 / 1024.0 / 1024.0 / 1024.0,
                total as f64 / 1024.0 / 1024.0 / 1024.0
            )
        } else {
            "Downloading the update".to_string()
        }
    };
    if pct == state.last_pct
        && detail == state.last_detail
        && state
            .last_emit
            .is_some_and(|last| last.elapsed() < Duration::from_secs(1))
    {
        return None;
    }
    state.last_pct = pct;
    state.last_detail = detail.clone();
    state.last_emit = Some(std::time::Instant::now());
    Some(format!(
        "KYTH_STAGE_PROGRESS pct={pct} phase={phase} detail={detail}"
    ))
}

fn emit_stage_phase(pct: u8, phase: &str, detail: &str) {
    println!("{}", stage_phase_marker(pct, phase, detail));
    let _ = std::io::Write::flush(&mut std::io::stdout());
}

fn stage_phase_marker(pct: u8, phase: &str, detail: &str) -> String {
    format!("KYTH_STAGE_PROGRESS pct={pct} phase={phase} detail={detail}")
}

/// Run `bootc upgrade` as its own process group so termination reaches
/// forked grandchildren. On SIGTERM the group gets SIGTERM, up to 10s to
/// exit gracefully, then SIGKILL; the caller reports failure and records
/// nothing.
fn run_bootc_child() -> Result<std::process::Output, String> {
    match run_bootc_child_with(true) {
        // A bootc that predates `--progress-fd` rejects it before doing any
        // work. Staging without live byte progress beats not staging at all.
        Ok(output)
            if !output.status.success()
                && String::from_utf8_lossy(&output.stderr)
                    .contains("unexpected argument '--progress-fd'") =>
        {
            run_bootc_child_with(false)
        }
        other => other,
    }
}

/// Create the pipe bootc writes its JSON progress to. Both ends are
/// close-on-exec; the child gets the write end re-exposed as fd 3 below.
fn progress_pipe() -> Option<(std::fs::File, libc::c_int)> {
    use std::os::fd::FromRawFd;
    let mut fds = [0 as libc::c_int; 2];
    // SAFETY: `fds` is a valid 2-element array for pipe2 to fill.
    if unsafe { libc::pipe2(fds.as_mut_ptr(), libc::O_CLOEXEC) } != 0 {
        return None;
    }
    // SAFETY: fds[0] is a fresh descriptor we own exclusively.
    Some((unsafe { std::fs::File::from_raw_fd(fds[0]) }, fds[1]))
}

/// Make `write_fd` appear as fd `BOOTC_PROGRESS_FD` in the child.
fn expose_progress_fd(command: &mut std::process::Command, write_fd: libc::c_int) {
    // SAFETY: only async-signal-safe calls (dup2/fcntl) between fork and exec.
    unsafe {
        command.pre_exec(move || {
            if write_fd == BOOTC_PROGRESS_FD {
                // dup2 onto itself is a no-op and would keep CLOEXEC set.
                let flags = libc::fcntl(write_fd, libc::F_GETFD);
                if flags < 0 || libc::fcntl(write_fd, libc::F_SETFD, flags & !libc::FD_CLOEXEC) < 0
                {
                    return Err(std::io::Error::last_os_error());
                }
            } else if libc::dup2(write_fd, BOOTC_PROGRESS_FD) < 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
}

/// Undo the parent's SIGTERM block in the upgrade child.
/// `arm_sigterm_forwarder` blocks SIGTERM process-wide for its sigwait-based
/// cancel watcher; the child inherits the blocked mask across fork+exec, which
/// would make the cancel path's `killpg(pgid, SIGTERM)` a no-op and force
/// every cancel through the SIGKILL grace wait. Unblocking here (between fork
/// and exec) lets the child die promptly on cancel.
fn unblock_sigterm_for_child(command: &mut std::process::Command) {
    // SAFETY: pthread_sigmask/sigemptyset/sigaddset are async-signal-safe and
    // only touch stack memory between fork and exec.
    unsafe {
        command.pre_exec(|| {
            let mut set: libc::sigset_t = std::mem::zeroed();
            libc::sigemptyset(&mut set);
            libc::sigaddset(&mut set, libc::SIGTERM);
            if libc::pthread_sigmask(libc::SIG_UNBLOCK, &set, std::ptr::null_mut()) != 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
}

fn run_bootc_child_with(live_progress: bool) -> Result<std::process::Output, String> {
    let mut command = std::process::Command::new("/usr/bin/bootc");
    command.arg("upgrade");
    // bootc hides its progress bars when stderr is not a terminal, so the
    // stderr parser never sees byte counts. `--progress-fd` is the supported
    // machine-readable channel for exactly this.
    let progress = if live_progress { progress_pipe() } else { None };
    if let Some((_, write_fd)) = &progress {
        command
            .arg("--progress-fd")
            .arg(BOOTC_PROGRESS_FD.to_string());
        expose_progress_fd(&mut command, *write_fd);
    }
    // Unconditional: the progress-fd pre_exec above only runs when live
    // progress is on, but the inherited SIGTERM block affects every spawn.
    unblock_sigterm_for_child(&mut command);
    command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    command.process_group(0);
    let spawned = command.spawn();
    // The parent must drop its copy of the write end or the reader never sees
    // EOF. Do this whether or not the spawn worked.
    let json_reader = progress.map(|(read, write_fd)| {
        // SAFETY: write_fd is the descriptor pipe2 returned; closed exactly once.
        unsafe { libc::close(write_fd) };
        std::thread::spawn(move || drain_json_progress(read))
    });
    let mut child = spawned.map_err(|error| format!("bootc upgrade could not start: {error}"))?;
    // Drain pipes on helper threads: bootc is chatty and a full pipe would
    // wedge the child while we poll below.
    let mut stdout = child.stdout.take();
    let mut stderr = child.stderr.take();
    let stdout_reader = std::thread::spawn(move || drain_pipe(&mut stdout));
    let stderr_reader = std::thread::spawn(move || drain_stderr_with_progress(&mut stderr));
    let started = std::time::Instant::now();
    let mut term_at: Option<std::time::Instant> = None;
    loop {
        if let Some(status) = child
            .try_wait()
            .map_err(|error| format!("bootc upgrade could not be reaped: {error}"))?
        {
            let stdout = stdout_reader.join().unwrap_or_default();
            let stderr = stderr_reader.join().unwrap_or_default();
            if let Some(reader) = json_reader {
                let _ = reader.join();
            }
            if CANCELLED.load(Ordering::SeqCst) {
                scrub_dracut_scratch();
                return Err(
                    "bootc upgrade was terminated and did not complete; nothing was staged"
                        .to_string(),
                );
            }
            return Ok(std::process::Output {
                status,
                stdout,
                stderr,
            });
        }
        if CANCELLED.load(Ordering::SeqCst) && term_at.is_none() {
            term_at = Some(std::time::Instant::now());
            let pgid = child.id() as libc::pid_t;
            unsafe {
                libc::killpg(pgid, libc::SIGTERM);
            }
        }
        if let Some(since_term) = term_at {
            if since_term.elapsed() > TERM_GRACE {
                let pgid = child.id() as libc::pid_t;
                unsafe {
                    libc::killpg(pgid, libc::SIGKILL);
                }
                let _ = child.wait();
                let _ = stdout_reader.join();
                let _ = stderr_reader.join();
                scrub_dracut_scratch();
                return Err(
                    "bootc upgrade was terminated and did not complete; nothing was staged"
                        .to_string(),
                );
            }
            std::thread::sleep(Duration::from_millis(25));
            continue;
        }
        if started.elapsed() > BOOTC_TIMEOUT {
            kyth_shared::system::process::kill_process_group(&mut child);
            let _ = stdout_reader.join();
            let _ = stderr_reader.join();
            scrub_dracut_scratch();
            return Err("bootc upgrade timed out; retry later".into());
        }
        std::thread::sleep(Duration::from_millis(25));
    }
}

fn run_upgrade() -> Result<String, String> {
    check_free("/sysroot", REQUIRED_FREE_BYTES)?;
    check_free("/boot", BOOT_FREE_MIN_BYTES)?;
    check_free("/var/tmp", REQUIRED_FREE_BYTES)?;
    kyth_shared::system::bootc_guard::with_bootc_lock(|| {
        emit_stage_phase(1, "download", "Starting image download");
        match run_bootc_child() {
            Ok(output) if output.status.success() => Ok(output_text(&output)),
            Ok(output) => {
                scrub_dracut_scratch();
                Err(output_text(&output))
            }
            Err(error) => {
                scrub_dracut_scratch();
                Err(error)
            }
        }
    })
}

fn upgrade() -> Result<String, String> {
    if !rustix::process::getuid().is_root() {
        return Err("kyth-safe-upgrade must run as root".into());
    }
    arm_sigterm_forwarder();
    let status = kyth_shared::system::bootc_query::fetch_status_data()
        .ok_or_else(|| "Could not determine the booted image status".to_string())?;
    let reference = kyth_shared::system::bootc_query::image_reference_from_status(&status)
        .ok_or_else(|| "Could not determine the booted image reference".to_string())?;
    // Do not make staging depend on a second registry client. GHCR metadata
    // probes can time out while bootc itself can still reach the image; bootc
    // is the authoritative fetcher for the mutating update path.
    let state = kyth_shared::system::boot_health::read_default_state();
    // Strict ring validation keeps the last known ring on unknown values:
    // resolve against the stored state before staging anything.
    let ring = rollout_ring(&state.rollout_ring)?;
    if let Some(reason) = kyth_shared::system::boot_health::rollout_policy_reason(&reference, &ring)
    {
        return Err(format!("Update blocked by rollout policy: {reason}"));
    }
    if let Some(reason) = kyth_shared::system::safe_upgrade_policy::battery_gate_reason() {
        return Err(reason);
    }
    let booted = kyth_shared::system::bootc_query::image_digest_from_status(&status, "booted");
    // Record the booted release (version and digest) before staging so the
    // post-upgrade gate can refuse a staged image older than what is
    // running, unless an explicit downgrade opt-in is present.
    let booted_version =
        kyth_shared::system::bootc_query::image_version_from_status(&status, "booted");
    let staged = kyth_shared::system::bootc_query::image_digest_from_status(&status, "staged");
    if let Some(reason) = staged
        .as_deref()
        .and_then(|digest| kyth_shared::system::boot_health::quarantine_reason(&state, digest))
    {
        return Err(format!("Update blocked: {reason}"));
    }
    if kyth_shared::system::bootc_query::active_operation().is_some() {
        return Err("Another bootc upgrade is in progress; retry later".into());
    }
    let detail = run_upgrade().map_err(|error| {
        scrub_dracut_scratch();
        error
    })?;
    if CANCELLED.load(Ordering::SeqCst) {
        scrub_dracut_scratch();
        return Err(
            "bootc upgrade was terminated and did not complete; nothing was staged".to_string(),
        );
    }
    let after = kyth_shared::system::bootc_query::fetch_status_data();
    let staged_after = after.as_ref().and_then(|data| {
        kyth_shared::system::bootc_query::image_digest_from_status(data, "staged")
    });
    let staged_quarantine_reason = staged_after.as_deref().and_then(|digest| {
        let state = kyth_shared::system::boot_health::read_default_state();
        kyth_shared::system::boot_health::quarantine_reason(&state, digest)
    });
    let post_upgrade = kyth_shared::system::safe_upgrade_policy::validate_post_upgrade_state(
        booted.as_deref(),
        after
            .as_ref()
            .and_then(|data| {
                kyth_shared::system::bootc_query::image_digest_from_status(data, "booted")
            })
            .as_deref(),
        staged_after.as_deref(),
        staged_quarantine_reason.as_deref(),
    )?;
    let Some(staged_digest) = post_upgrade else {
        return Ok(if detail.is_empty() {
            "KythOS is already running the latest allowed digest.".into()
        } else {
            detail
        });
    };
    emit_stage_phase(
        99,
        "verify",
        "Verifying the staged image and checking its safety policy",
    );
    // Refuse a staged image older than the recorded booted release unless an
    // explicit downgrade opt-in is present.
    let allow_downgrade = std::fs::read_to_string(DEFAULT_CONFIG)
        .map(|raw| kyth_shared::system::safe_upgrade_policy::allow_downgrade_from_toml(&raw))
        .unwrap_or_else(|_| {
            kyth_shared::system::safe_upgrade_policy::allow_downgrade_from_toml("")
        });
    kyth_shared::system::safe_upgrade_policy::validate_not_downgrade(
        booted_version.as_deref(),
        booted.as_deref(),
        after
            .as_ref()
            .and_then(|data| {
                kyth_shared::system::bootc_query::image_version_from_status(data, "staged")
            })
            .as_deref(),
        staged_after.as_deref(),
        allow_downgrade,
    )?;
    let coordinator = kyth_shared::system::update_coordinator::UpdateCoordinator::new(
        kyth_shared::system::boot_health::DEFAULT_STATE_PATH,
    );
    coordinator
        .record_staged(
            &staged_digest,
            kyth_shared::system::boot_health::image_ring(&reference).unwrap_or(&ring),
            now(),
        )
        .map_err(|error| format!("Could not persist staged update state: {error}"))?;
    check_free("/var/cache", VAR_CACHE_FREE_MIN_BYTES)?;
    emit_stage_phase(
        99,
        "finalize",
        "Preparing the staged deployment for the next boot",
    );
    let finalized = kyth_shared::system::boot_finalize::finalize_staged(false)?;
    Ok(if finalized.is_empty() {
        if detail.is_empty() {
            "Update staged and promoted to the next boot.".into()
        } else {
            detail
        }
    } else {
        finalized
    })
}

fn main() -> std::process::ExitCode {
    if std::env::args().nth(1).is_some() {
        eprintln!("kyth-safe-upgrade accepts no arguments");
        return std::process::ExitCode::from(64);
    }
    match upgrade() {
        Ok(detail) => {
            if !detail.is_empty() {
                println!("{detail}");
            }
            std::process::ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{error}");
            std::process::ExitCode::from(1)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bootc_download_json_drives_a_real_percentage() {
        // Event shapes from bootc's progress_jsonl.rs (task "pulling").
        let mut state = JsonProgress::default();
        let pull = |bytes: u64, steps: u64| {
            format!(
                "{{\"type\":\"ProgressBytes\",\"task\":\"pulling\",\"description\":\"Pulling Image: sha256:ab\",\"id\":\"sha256:ab\",\"bytesCached\":0,\"bytes\":{bytes},\"bytesTotal\":4000000000,\"stepsCached\":30,\"steps\":{steps},\"stepsTotal\":39,\"subtasks\":[]}}"
            )
        };
        let first = classify_progress_json(&pull(40_000_000, 0), &mut state).unwrap();
        assert!(
            first.starts_with("KYTH_STAGE_PROGRESS pct=1 phase=download "),
            "{first}"
        );
        let half = classify_progress_json(&pull(2_000_000_000, 20), &mut state).unwrap();
        assert!(
            half.starts_with("KYTH_STAGE_PROGRESS pct=42 phase=download "),
            "{half}"
        );
        assert!(half.contains("Downloading layer 21 of 39"), "{half}");
        assert!(half.contains("1907 MiB of 3815 MiB"), "{half}");
        let done = classify_progress_json(&pull(4_000_000_000, 39), &mut state).unwrap();
        assert!(
            done.starts_with("KYTH_STAGE_PROGRESS pct=85 phase=download "),
            "{done}"
        );
        // A stale, lower reading must never drag the bar backwards.
        assert!(classify_progress_json(&pull(1_000_000_000, 10), &mut state).is_none());
        // Identical repeat is suppressed.
        assert!(classify_progress_json(&pull(4_000_000_000, 39), &mut state).is_none());
    }

    #[test]
    fn bootc_import_json_moves_past_download_only_after_the_download_share() {
        let mut state = JsonProgress::default();
        let importing = |steps: u64| {
            format!(
                "{{\"type\":\"ProgressSteps\",\"task\":\"importing\",\"description\":\"Importing Image\",\"id\":\"x\",\"stepsCached\":0,\"steps\":{steps},\"stepsTotal\":1,\"subtasks\":[]}}"
            )
        };
        let start = classify_progress_json(&importing(0), &mut state).unwrap();
        assert!(
            start.starts_with("KYTH_STAGE_PROGRESS pct=86 phase=install "),
            "{start}"
        );
        let end = classify_progress_json(&importing(1), &mut state).unwrap();
        assert!(
            end.starts_with("KYTH_STAGE_PROGRESS pct=88 phase=install "),
            "{end}"
        );
    }

    #[test]
    fn bootc_json_ignores_unknown_and_garbled_lines() {
        let mut state = JsonProgress::default();
        for line in [
            "",
            "not json",
            "{\"type\":\"Start\",\"version\":\"0.1.0\"}",
            "{\"type\":\"ProgressSteps\",\"task\":\"deploying\"}",
            "{\"task\":\"pulling\"}",
            "[1,2,3]",
        ] {
            assert!(classify_progress_json(line, &mut state).is_none(), "{line}");
        }
        assert_eq!(state.last_pct, 0);
    }

    #[test]
    fn bootc_json_pull_retry_keeps_the_bar_where_it_was() {
        let mut state = JsonProgress::default();
        let bytes = "{\"type\":\"ProgressBytes\",\"task\":\"pulling\",\"description\":\"d\",\"id\":\"i\",\"bytesCached\":0,\"bytes\":2000,\"bytesTotal\":4000,\"stepsCached\":0,\"steps\":1,\"stepsTotal\":2,\"subtasks\":[]}";
        classify_progress_json(bytes, &mut state).unwrap();
        let retry = "{\"type\":\"ProgressSteps\",\"task\":\"pulling\",\"description\":\"Container image pull failed; retrying in 5 seconds (1/3)\",\"id\":\"pull-retry\",\"stepsCached\":0,\"steps\":1,\"stepsTotal\":3,\"subtasks\":[]}";
        let marker = classify_progress_json(retry, &mut state).unwrap();
        assert!(
            marker.starts_with("KYTH_STAGE_PROGRESS pct=42 phase=download "),
            "{marker}"
        );
        assert!(marker.contains("retrying in 5 seconds"), "{marker}");
    }

    #[test]
    fn progress_fd_reaches_a_real_child_and_ends_at_eof() {
        // Same pipe + dup2 wiring as the bootc spawn, with sh standing in.
        let (read, write_fd) = progress_pipe().expect("pipe");
        let mut command = std::process::Command::new("sh");
        command.args([
            "-c",
            "printf '%s\\n' '{\"type\":\"ProgressBytes\",\"task\":\"pulling\",\"description\":\"d\",\"id\":\"i\",\"bytesCached\":0,\"bytes\":1,\"bytesTotal\":2,\"stepsCached\":0,\"steps\":0,\"stepsTotal\":1,\"subtasks\":[]}' >&3",
        ]);
        expose_progress_fd(&mut command, write_fd);
        let mut child = command.spawn().expect("spawn sh");
        // Parent closes its write end, as run_bootc_child_with does.
        unsafe { libc::close(write_fd) };
        let mut text = String::new();
        std::io::Read::read_to_string(&mut std::io::BufReader::new(read), &mut text)
            .expect("reader reaches EOF once the child exits");
        assert!(child.wait().unwrap().success());
        let mut state = JsonProgress::default();
        let marker = classify_progress_json(text.trim(), &mut state).expect("marker");
        assert!(
            marker.starts_with("KYTH_STAGE_PROGRESS pct=42 phase=download "),
            "{marker}"
        );
    }

    #[test]
    fn download_phase_marker_uses_the_frontend_progress_contract() {
        assert_eq!(
            stage_phase_marker(1, "download", "Starting image download"),
            "KYTH_STAGE_PROGRESS pct=1 phase=download detail=Starting image download"
        );
    }

    #[test]
    fn space_minimums_match_policy() {
        assert_eq!(BOOT_FREE_MIN_BYTES / (1024 * 1024), 500);
        assert_eq!(REQUIRED_FREE_BYTES / (1024 * 1024), 2048);
        assert_eq!(VAR_CACHE_FREE_MIN_BYTES / (1024 * 1024), 500);
    }

    #[test]
    fn term_grace_is_ten_seconds() {
        assert_eq!(TERM_GRACE, Duration::from_secs(10));
    }

    fn feed(lines: &[&str]) -> (StageProgress, Vec<String>) {
        let mut state = StageProgress::default();
        let markers = lines
            .iter()
            .filter_map(|line| classify_bootc_fragment(line, &mut state))
            .collect();
        (state, markers)
    }

    #[test]
    fn progress_reader_emits_carriage_return_updates_without_waiting_for_newline() {
        let input = b"download 10%\rdownload 20%\r\ninstall\n";
        let mut reader = std::io::BufReader::new(std::io::Cursor::new(input));
        let mut fragment = Vec::new();
        let mut fragments = Vec::new();
        loop {
            match read_progress_fragment(&mut reader, &mut fragment, 128).unwrap() {
                Some(_) => fragments.push(String::from_utf8_lossy(&fragment).to_string()),
                None => break,
            }
        }
        assert_eq!(
            fragments,
            ["download 10%\r", "download 20%\r", "\n", "install\n"]
        );
    }

    #[test]
    fn progress_reader_caps_oversized_fragments_and_drains_them() {
        let input = format!("{}\rnext\n", "x".repeat(1024));
        let mut reader = std::io::BufReader::new(std::io::Cursor::new(input.into_bytes()));
        let mut fragment = Vec::new();
        assert_eq!(
            read_progress_fragment(&mut reader, &mut fragment, 32).unwrap(),
            Some(true)
        );
        assert_eq!(fragment.len(), 32);
        assert_eq!(
            read_progress_fragment(&mut reader, &mut fragment, 32).unwrap(),
            Some(false)
        );
        assert_eq!(String::from_utf8_lossy(&fragment), "next\n");
    }

    #[test]
    fn stdout_drain_caps_capture_but_reads_the_entire_pipe() {
        let input = vec![b'x'; MAX_CAPTURE_BYTES + 128];
        let cursor = std::io::Cursor::new(input.clone());
        let mut pipe = Some(cursor);
        let captured = drain_pipe(&mut pipe);
        assert_eq!(pipe.as_ref().unwrap().position(), input.len() as u64);
        assert_eq!(&captured[..MAX_CAPTURE_BYTES], &input[..MAX_CAPTURE_BYTES]);
        assert!(captured.ends_with(b"\n...[truncated]"));
    }

    #[test]
    fn layers_needed_sets_totals_and_counts_starts() {
        let (state, markers) = feed(&[
            "layers already present: 30; layers needed: 39 (4.4 GB)",
            "Copying blob sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "Copying blob sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ]);
        assert_eq!(state.blobs_needed, 39);
        assert_eq!(state.blobs_started.len(), 2);
        assert_eq!(state.pct().0, (85.0 * 1.0 / 39.0) as u8);
        assert!(!markers.is_empty());
    }

    #[test]
    fn indicatif_bar_tracks_bytes_and_never_regresses() {
        let (state, _) = feed(&[
            "a1b2c3d4e5f6 [======>---------------------] 250MiB / 500MiB (10MiB/s)",
            "a1b2c3d4e5f6 [============>---------------] 400MiB / 500MiB (10MiB/s)",
            "a1b2c3d4e5f6 [======>---------------------] 250MiB / 500MiB (10MiB/s)",
        ]);
        assert_eq!(state.downloaded_bytes(), 400 * 1024 * 1024);
        assert_eq!(state.total_bytes(), 500 * 1024 * 1024);
        assert_eq!(state.pct().0, (85.0 * 0.8) as u8);
    }

    #[test]
    fn blob_done_lines_advance_past_starts() {
        let (state, _) = feed(&[
            "layers already present: 0; layers needed: 4 (1.0 GB)",
            "Copying blob 797644653c72 skipped: already exists",
            "Copying blob ef5675472650 done",
        ]);
        assert_eq!(state.blobs_done, 2);
        assert_eq!(state.pct().0, (85.0 * 2.0 / 4.0) as u8);
    }

    #[test]
    fn deploy_lines_move_to_install_phase_capped_at_99() {
        let (state, markers) = feed(&[
            "Writing manifest to image destination",
            "Merging layer 1/39: overlay diff",
            "Writing commit",
            "dracut: building initramfs",
        ]);
        let (pct, phase) = state.pct();
        assert_eq!(phase, "install");
        assert!(pct >= 85 && pct <= 99, "pct={pct}");
        assert!(markers.iter().any(|m| m.contains("phase=install")));
    }

    #[test]
    fn noise_lines_emit_only_the_initial_activity_marker() {
        let (state, markers) = feed(&[
            "Getting image source signatures",
            "Checking out base commit",
            "",
            "   ",
        ]);
        // The first fragment announces activity at 0%; repeats stay silent.
        assert_eq!(markers.len(), 1);
        assert!(markers[0].contains("pct=0"));
        assert_eq!(state.pct().0, 0);
    }

    #[test]
    fn marker_format_is_parseable() {
        let (_, markers) = feed(&[
            "Copying blob sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        ]);
        let marker = markers.into_iter().next().expect("start line emits");
        assert!(marker.starts_with("KYTH_STAGE_PROGRESS pct="));
        assert!(marker.contains(" phase=download detail="));
    }
}
