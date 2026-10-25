use std::process::Command;
use std::sync::OnceLock;
use std::time::Duration;

use serde::{Deserialize, Serialize};

use kyth_shared::system::jobs::{timeout_for, JobStore, JobTimeoutClass};

static HUB_ACTION_JOBS: OnceLock<JobStore> = OnceLock::new();
static UPDATE_JOBS: OnceLock<JobStore> = OnceLock::new();

fn hub_action_jobs() -> &'static JobStore {
    HUB_ACTION_JOBS.get_or_init(JobStore::default)
}

fn update_jobs() -> &'static JobStore {
    UPDATE_JOBS.get_or_init(JobStore::default)
}

/// In-process slot for mutating update launches (stage/rollback/switch/
/// apply). Without it, two rapid invocations (double-click, two tabs)
/// would each spawn a `sudo -A` job — stacked prompts racing on
/// finalize. The slot closes that window: the second launch fails fast
/// with the busy wording below. The slot is this shell's only admission
/// control; the shell itself must never probe the root-only bootc lock
/// (see the regression test at the bottom of this file). Cross-process
/// serialization is layered underneath: the stage and switch helpers
/// hold the bootc flock for their whole run, rollback invokes `bootc`
/// directly with no flock, and every path ultimately rests on
/// bootc/ostree's internal sysroot lock, which refuses a second
/// concurrent writer.
static UPDATE_MUTATING: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

struct MutatingSlot;

impl Drop for MutatingSlot {
    fn drop(&mut self) {
        UPDATE_MUTATING.store(false, std::sync::atomic::Ordering::SeqCst);
    }
}

fn take_mutating_slot() -> Result<MutatingSlot, String> {
    UPDATE_MUTATING
        .compare_exchange(
            false,
            true,
            std::sync::atomic::Ordering::SeqCst,
            std::sync::atomic::Ordering::SeqCst,
        )
        .map(|_| MutatingSlot)
        // Nothing retries this automatically — the old wording implied a
        // background retry that doesn't exist. Every caller of this slot
        // (stage/apply/rollback/switch) surfaces this string, and not all of
        // them pass it through a translation layer, so the message itself
        // has to be accurate rather than relying on the frontend to fix it.
        .map_err(|_| {
            "Another system update operation is already in progress. Wait for it to finish, or check its status, before trying again.".to_string()
        })
}

/// Binary precheck shared by the mutating launchers: fail before a job
/// (and its sudo prompt) exists when the binary the launcher is about to
/// run is absent, instead of spawning a job that dies on exec.
fn require_binary(path: &str, missing: &str) -> Result<(), String> {
    if std::path::Path::new(path).exists() {
        Ok(())
    } else {
        Err(missing.to_string())
    }
}

/// Latest live staging progress, streamed from `kyth-safe-upgrade` marker
/// lines while the stage job runs. The Updates page polls `stage_progress`
/// for a determinate bar; `active` is false when no stage is running.
#[derive(Serialize, Clone)]
pub(crate) struct StageProgressSnapshot {
    pub(crate) pct: u8,
    pub(crate) phase: String,
    pub(crate) detail: String,
    pub(crate) active: bool,
}

static STAGE_PROGRESS: OnceLock<std::sync::Mutex<StageProgressSnapshot>> = OnceLock::new();
const STAGE_PROGRESS_HEARTBEAT: Duration = Duration::from_secs(5);
const IMAGE_RELEASES_API: &str = "https://api.github.com/repos/kyth-os/kyth/releases?per_page=100";
const IMAGE_RELEASES_MAX_BYTES: &str = "4000000";

#[derive(Debug, Clone, Serialize)]
pub(crate) struct UpdateReleaseSummary {
    pub(crate) version: String,
    pub(crate) flavor: String,
    pub(crate) release_url: String,
    pub(crate) highlights_title: String,
    pub(crate) highlights: Vec<String>,
    /// Number of package-change rows parsed from the release notes. The UI
    /// shows the complete list, so this equals the rendered package rows and
    /// lets the heading state the total (e.g. "Package changes (50)").
    pub(crate) package_total: usize,
}

fn valid_image_digest(digest: &str) -> bool {
    digest.strip_prefix("sha256:").is_some_and(|hex| {
        hex.len() == 64
            && hex
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    })
}

fn image_release_version(channel: &str, tag: &str) -> Option<String> {
    image_release_identity(channel, tag).map(|(version, _flavor)| version)
}

/// Channel image releases come in two kernel flavors sharing one version
/// string: `image-<channel>-<date>-<build>-<rev>-<sha>` (fedora) and
/// `image-<channel>-cachy-<date>-<build>-<rev>-<sha>` (cachy). The flavor
/// infix must parse too — without it a cachy install's own releases never
/// match, so its update notes silently never appear.
fn image_release_identity(channel: &str, tag: &str) -> Option<(String, &'static str)> {
    if !matches!(channel, "latest" | "testing") {
        return None;
    }
    let suffix = tag.strip_prefix(&format!("image-{channel}-"))?;
    let (flavor, suffix) = match suffix.strip_prefix("cachy-") {
        Some(rest) => ("cachy", rest),
        None => ("fedora", suffix),
    };
    let parts: Vec<&str> = suffix.split('-').collect();
    if parts.len() != 4
        || parts[0].len() != 8
        || !parts[0].bytes().all(|byte| byte.is_ascii_digit())
        || !parts[1..3]
            .iter()
            .all(|part| !part.is_empty() && part.bytes().all(|byte| byte.is_ascii_digit()))
        || parts[3].len() != 8
        || !parts[3]
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return None;
    }
    Some((
        format!(
            "{channel}.{}.{}.{}.{}",
            parts[0], parts[1], parts[2], parts[3]
        ),
        flavor,
    ))
}

fn release_cell(value: &str) -> Option<String> {
    let value = value.trim().trim_matches('`');
    if value.is_empty()
        || value.len() > 100
        || !value.bytes().all(|byte| {
            byte.is_ascii_alphanumeric()
                || matches!(byte, b'.' | b'_' | b'-' | b'+' | b'^' | b':' | b'~')
        })
    {
        return None;
    }
    Some(value.to_string())
}

fn release_highlights(body: &str) -> (String, Vec<String>, usize) {
    let mut section = "";
    let mut major_package_changes = Vec::new();
    let mut all_package_changes = Vec::new();
    let mut security_fixes = Vec::new();
    for line in body.lines() {
        if let Some(heading) = line.strip_prefix("### ") {
            section = heading.trim();
            continue;
        }
        let cells: Vec<&str> = line.split('|').map(str::trim).collect();
        if matches!(section, "Major Package Changes" | "All RPM Changes") && cells.len() >= 6 {
            let (Some(marker), Some(name)) = (release_cell(cells[1]), release_cell(cells[2]))
            else {
                continue;
            };
            let previous = release_cell(cells[3]);
            let next = release_cell(cells[4]);
            let change = match (marker.as_str(), previous, next) {
                ("+", None, Some(next)) => format!("Added {name} {next}"),
                ("-", Some(previous), None) => format!("Removed {name} {previous}"),
                ("~", Some(previous), Some(next)) => {
                    format!("Updated {name} from {previous} to {next}")
                }
                _ => continue,
            };
            if section == "Major Package Changes" {
                major_package_changes.push(change);
            } else {
                all_package_changes.push(change);
            }
        } else if section == "Security fixes" {
            for word in
                line.split(|character: char| !character.is_ascii_alphanumeric() && character != '-')
            {
                if word.starts_with("CVE-")
                    && word.len() <= 24
                    && word[4..]
                        .bytes()
                        .all(|byte| byte.is_ascii_digit() || byte == b'-')
                {
                    security_fixes.push(format!("Security fix: {word}"));
                }
            }
        }
    }
    let mut package_changes = if all_package_changes.is_empty() {
        major_package_changes
    } else {
        all_package_changes
    };
    // The pending preview and the history entry must show exactly which
    // packages change: return the complete list, never a silent sample. A
    // 50-row SBOM diff renders as 50 rows with package_total == 50.
    let package_total = package_changes.len();
    security_fixes.sort();
    security_fixes.dedup();
    if !package_changes.is_empty() {
        package_changes.extend(security_fixes);
        (
            "Package changes".to_string(),
            package_changes,
            package_total,
        )
    } else if !security_fixes.is_empty() {
        ("Security fixes".to_string(), security_fixes, 0)
    } else {
        ("Release highlights".to_string(), Vec::new(), 0)
    }
}

fn update_release_summary_from_api(
    payload: &str,
    channel: &str,
    digest: &str,
) -> Option<UpdateReleaseSummary> {
    if !valid_image_digest(digest) || !matches!(channel, "latest" | "testing") {
        return None;
    }
    let releases: serde_json::Value = serde_json::from_str(payload).ok()?;
    let releases = releases.as_array()?;
    let expected_digest_line = format!("Image: `ghcr.io/kyth-os/kyth@{digest}`");
    for release in releases {
        if release.get("draft").and_then(serde_json::Value::as_bool) != Some(false)
            || release
                .get("prerelease")
                .and_then(serde_json::Value::as_bool)
                != Some(channel == "testing")
        {
            continue;
        }
        let tag = release
            .get("tag_name")
            .and_then(serde_json::Value::as_str)?;
        let Some((version, flavor)) = image_release_identity(channel, tag) else {
            continue;
        };
        let body = release
            .get("body")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        if !body.lines().any(|line| line.trim() == expected_digest_line) {
            continue;
        }
        let (highlights_title, highlights, package_total) = release_highlights(body);
        return Some(UpdateReleaseSummary {
            version,
            flavor: flavor.to_string(),
            release_url: format!("https://github.com/kyth-os/kyth/releases/tag/{tag}"),
            highlights_title,
            highlights,
            package_total,
        });
    }
    None
}

fn fetch_image_releases_payload() -> Option<String> {
    let argv = vec![
        "curl".to_string(),
        "-fsSL".to_string(),
        "--max-time".to_string(),
        "12".to_string(),
        "--max-filesize".to_string(),
        IMAGE_RELEASES_MAX_BYTES.to_string(),
        "-H".to_string(),
        "Accept: application/vnd.github+json".to_string(),
        "-H".to_string(),
        "User-Agent: Kyth-Hub".to_string(),
        IMAGE_RELEASES_API.to_string(),
    ];
    let output = kyth_shared::system::process::run_bounded(&argv, Duration::from_secs(15)).ok()?;
    if !output.status.success() {
        return None;
    }
    Some(String::from_utf8_lossy(&output.stdout).into_owned())
}

/// Split an installed image branch into its release channel and kernel
/// flavor. `testing-cachy` is channel `testing`, flavor `cachy`: without
/// this mapping a CachyOS install's own releases never match, so its update
/// notes and history silently never appear.
fn normalize_image_branch(branch: &str) -> Option<(&'static str, &'static str)> {
    match branch {
        "latest" => Some(("latest", "fedora")),
        "testing" => Some(("testing", "fedora")),
        "latest-cachy" => Some(("latest", "cachy")),
        "testing-cachy" => Some(("testing", "cachy")),
        _ => None,
    }
}

fn current_image_channel() -> Option<String> {
    let branch = kyth_shared::system::bootc::current_branch()?;
    normalize_image_branch(branch.as_str()).map(|(channel, _flavor)| channel.to_string())
}

fn current_image_flavor() -> Option<&'static str> {
    let branch = kyth_shared::system::bootc::current_branch()?;
    normalize_image_branch(branch.as_str()).map(|(_channel, flavor)| flavor)
}

fn fetch_update_release_summary(digest: &str) -> Option<UpdateReleaseSummary> {
    if !valid_image_digest(digest) {
        return None;
    }
    let channel = current_image_channel()?;
    let payload = fetch_image_releases_payload()?;
    update_release_summary_from_api(&payload, &channel, digest)
}

#[tauri::command]
pub(crate) async fn update_release_summary(digest: String) -> Option<UpdateReleaseSummary> {
    tauri::async_runtime::spawn_blocking(move || fetch_update_release_summary(&digest))
        .await
        .ok()
        .flatten()
}

#[derive(Debug, Clone, Serialize)]
pub(crate) struct UpdateHistoryEntry {
    pub(crate) version: String,
    pub(crate) flavor: String,
    pub(crate) release_url: String,
    pub(crate) published_at: String,
    pub(crate) digest: String,
    pub(crate) highlights_title: String,
    pub(crate) highlights: Vec<String>,
    pub(crate) notes_intro: String,
    /// Number of package-change rows parsed from this release's notes; the
    /// entry renders all of them, so this is the honest total, not a sample.
    pub(crate) package_total: usize,
}

/// The digest a release body binds itself to, from its
/// `Image: ghcr.io/kyth-os/kyth@sha256:...` line; empty when absent.
fn release_body_digest(body: &str) -> String {
    for line in body.lines() {
        if let Some(rest) = line.trim().strip_prefix("Image: `ghcr.io/kyth-os/kyth@") {
            let digest = rest.trim_end_matches('`').trim();
            if valid_image_digest(digest) {
                return digest.to_string();
            }
        }
    }
    String::new()
}

/// Free-form prose is omitted from update history; the generated package
/// change table is the actionable summary, and inventories are not diffs.
fn release_notes_intro(_body: &str) -> String {
    String::new()
}

fn update_release_history_from_api(
    payload: &str,
    channel: &str,
    flavor: &str,
) -> Vec<UpdateHistoryEntry> {
    let Ok(releases) = serde_json::from_str::<serde_json::Value>(payload) else {
        return Vec::new();
    };
    let Some(releases) = releases.as_array() else {
        return Vec::new();
    };
    let mut entries = Vec::new();
    for release in releases {
        if release.get("draft").and_then(serde_json::Value::as_bool) != Some(false)
            || release
                .get("prerelease")
                .and_then(serde_json::Value::as_bool)
                != Some(channel == "testing")
        {
            continue;
        }
        let Some(tag) = release.get("tag_name").and_then(serde_json::Value::as_str) else {
            continue;
        };
        let Some((version, release_flavor)) = image_release_identity(channel, tag) else {
            continue;
        };
        // Fedora and CachyOS releases share version strings; only the
        // installed flavor's rows belong in this machine's history.
        if release_flavor != flavor {
            continue;
        }
        let body = release
            .get("body")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        let (highlights_title, highlights, package_total) = release_highlights(body);
        entries.push(UpdateHistoryEntry {
            version,
            flavor: release_flavor.to_string(),
            release_url: format!("https://github.com/kyth-os/kyth/releases/tag/{tag}"),
            published_at: release
                .get("published_at")
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default()
                .to_string(),
            digest: release_body_digest(body),
            highlights_title,
            highlights,
            notes_intro: release_notes_intro(body),
            package_total,
        });
        if entries.len() >= 20 {
            break;
        }
    }
    entries
}

fn fetch_update_release_history() -> Vec<UpdateHistoryEntry> {
    let Some(channel) = current_image_channel() else {
        return Vec::new();
    };
    let Some(flavor) = current_image_flavor() else {
        return Vec::new();
    };
    let Some(payload) = fetch_image_releases_payload() else {
        return Vec::new();
    };
    update_release_history_from_api(&payload, &channel, flavor)
}

#[tauri::command]
pub(crate) async fn update_release_history() -> Vec<UpdateHistoryEntry> {
    tauri::async_runtime::spawn_blocking(fetch_update_release_history)
        .await
        .unwrap_or_default()
}

fn stage_progress_cell() -> &'static std::sync::Mutex<StageProgressSnapshot> {
    STAGE_PROGRESS.get_or_init(|| {
        std::sync::Mutex::new(StageProgressSnapshot {
            pct: 0,
            phase: "download".into(),
            detail: "Starting the download…".into(),
            active: false,
        })
    })
}

/// Parse a `KYTH_STAGE_PROGRESS pct=N phase=P detail=…` marker line.
fn parse_stage_marker(line: &str) -> Option<StageProgressSnapshot> {
    let rest = line.strip_prefix("KYTH_STAGE_PROGRESS ")?;
    let pct = rest
        .split_whitespace()
        .find_map(|token| token.strip_prefix("pct=")?.parse::<u8>().ok())?;
    let phase = rest
        .split_whitespace()
        .find_map(|token| token.strip_prefix("phase="))
        .unwrap_or("download")
        .to_string();
    let detail = rest
        .find("detail=")
        .map(|idx| rest[idx + "detail=".len()..].trim().to_string())
        .filter(|text| !text.is_empty())
        .unwrap_or_else(|| {
            if phase == "install" {
                "Installing the staged image…".to_string()
            } else {
                "Downloading the update…".to_string()
            }
        });
    Some(StageProgressSnapshot {
        pct: pct.min(99),
        phase,
        detail,
        active: true,
    })
}

/// Merge a streamed marker into the current snapshot. Pure so the
/// monotonic clamp is unit-testable: a retried marker must never drag the
/// bar backwards.
fn merge_stage_snapshot(
    current: &StageProgressSnapshot,
    next: StageProgressSnapshot,
) -> StageProgressSnapshot {
    if next.pct >= current.pct {
        next
    } else {
        current.clone()
    }
}

/// Read one process-output line without letting an unterminated line allocate
/// without bound. Oversized lines are drained, capped, and never interpreted
/// as progress markers.
fn read_stage_line(
    reader: &mut impl std::io::BufRead,
    line: &mut Vec<u8>,
    limit: usize,
) -> std::io::Result<Option<bool>> {
    line.clear();
    let mut truncated = false;
    loop {
        let available = reader.fill_buf()?;
        if available.is_empty() {
            return Ok(if line.is_empty() && !truncated {
                None
            } else {
                Some(truncated)
            });
        }
        let consumed = available
            .iter()
            .position(|byte| *byte == b'\n')
            .map_or(available.len(), |index| index + 1);
        let remaining = limit.saturating_sub(line.len());
        let copied = consumed.min(remaining);
        line.extend_from_slice(&available[..copied]);
        truncated |= copied < consumed;
        let ended = available[consumed - 1] == b'\n';
        reader.consume(consumed);
        if ended {
            return Ok(Some(truncated));
        }
    }
}

/// Capture only a bounded prefix while continuing to drain the child pipe.
/// Closing a pipe at the capture limit can make a verbose helper fail with
/// EPIPE before it reaches its real result.
fn collect_bounded_output(
    reader: &mut impl std::io::Read,
    limit: usize,
) -> std::io::Result<Vec<u8>> {
    let mut collected = Vec::with_capacity(limit);
    let mut buffer = [0u8; 8192];
    let mut truncated = false;
    loop {
        let count = reader.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        let room = limit.saturating_sub(collected.len());
        let copied = count.min(room);
        collected.extend_from_slice(&buffer[..copied]);
        truncated |= copied < count;
    }
    if truncated {
        collected.extend_from_slice(b"\n...[truncated]");
    }
    Ok(collected)
}

#[tauri::command]
pub(crate) fn stage_progress() -> StageProgressSnapshot {
    stage_progress_cell()
        .lock()
        .map(|snapshot| snapshot.clone())
        .unwrap_or(StageProgressSnapshot {
            pct: 0,
            phase: "download".into(),
            detail: "Starting the download…".into(),
            active: false,
        })
}

/// How long the stage worker waits for a pipe-reader thread to deliver
/// its capture after the helper has exited or been killed. Readers
/// normally deliver the moment their pipe hits EOF; the grace only
/// matters when a grandchild escaped the process-group kill and keeps
/// a pipe open — then the worker proceeds without that capture and the
/// reader detaches (its send fails into a dropped receiver) instead of
/// wedging `finish()` — and with it the mutating slot — forever.
const STAGE_READER_JOIN_GRACE: Duration = Duration::from_secs(2);

/// RAII backstop for the stage progress snapshot: dropping it marks the
/// snapshot inactive. The stage worker clears `active` explicitly before
/// finishing its job; this guard covers the paths where it cannot (a
/// panic unwinding the worker), so the Updates page never polls a
/// phantom "still staging" snapshot until the Hub restarts. The worker
/// declares it AFTER the mutating slot, so it drops FIRST: the snapshot
/// reads inactive before the slot frees the next stage launch.
struct StageProgressGuard;

impl Drop for StageProgressGuard {
    fn drop(&mut self) {
        if let Ok(mut snapshot) = stage_progress_cell().lock() {
            snapshot.active = false;
        }
    }
}

/// Collect one stage pipe reader's capture, waiting at most
/// [`STAGE_READER_JOIN_GRACE`] for it (see the constant). A missing pipe
/// resolves to empty immediately.
fn join_stage_reader(receiver: Option<std::sync::mpsc::Receiver<Vec<u8>>>) -> Vec<u8> {
    receiver
        .and_then(|rx| rx.recv_timeout(STAGE_READER_JOIN_GRACE).ok())
        .unwrap_or_default()
}

/// Worker body for [`start_stage_job`]: spawn the helper, stream its
/// progress markers into the snapshot, and resolve the job entry. The
/// caller wraps this in `catch_unwind` and owns the mutating slot and
/// the progress guard, so a panic here still finishes the job instead
/// of wedging it at `running`.
fn run_stage_worker(
    job: &str,
    operation: &str,
    argv: Vec<String>,
    timeout: Duration,
    cancel: std::sync::Arc<std::sync::atomic::AtomicBool>,
) {
    let operation_for_thread = operation.to_string();
    let progress_activity = std::sync::Arc::new(std::sync::Mutex::new(std::time::Instant::now()));
    use std::os::unix::process::CommandExt;
    let mut command = Command::new(&argv[0]);
    command.args(&argv[1..]);
    let inherited = std::env::vars().collect::<std::collections::BTreeMap<_, _>>();
    let desktop = kyth_shared::commands::environment_for(
        kyth_shared::commands::EnvironmentPolicy::Desktop,
        &inherited,
    );
    command.env_clear().envs(desktop);
    if std::path::Path::new("/usr/bin/ksshaskpass").exists() {
        command.env("SUDO_ASKPASS", "/usr/bin/ksshaskpass");
    }
    command.process_group(0);
    command.stdin(std::process::Stdio::null());
    command.stdout(std::process::Stdio::piped());
    command.stderr(std::process::Stdio::piped());
    let spawned = command.spawn();
    let (state, detail) = match spawned {
        Ok(mut child) => {
            // Both pipes drain on helper threads from the start: a
            // chatty helper (>64 KiB on either pipe) must never wedge
            // the child, and cancel/timeout must preempt mid-download
            // instead of waiting for EOF. Captures are capped at 1 MiB
            // each (overflow is truncated and marked). A bounded line
            // reader also prevents a newline-free child write from
            // forcing `read_line` to allocate the entire pipe payload.
            const MAX_STAGE_CAPTURE_BYTES: usize = 1024 * 1024;
            const MAX_STAGE_LINE_BYTES: usize = 64 * 1024;
            let stderr_rx = child.stderr.take().map(|stderr| {
                let (tx, rx) = std::sync::mpsc::channel::<Vec<u8>>();
                std::thread::spawn(move || {
                    let mut reader = std::io::BufReader::new(stderr);
                    let collected = collect_bounded_output(&mut reader, MAX_STAGE_CAPTURE_BYTES)
                        .unwrap_or_default();
                    // If the join grace already expired, the receiver
                    // is gone and the capture is simply discarded.
                    let _ = tx.send(collected);
                });
                rx
            });
            let stdout_rx = child.stdout.take().map(|stdout| {
                let (tx, rx) = std::sync::mpsc::channel::<Vec<u8>>();
                let progress_activity = progress_activity.clone();
                std::thread::spawn(move || {
                    let mut collected_out = Vec::new();
                    let mut reader = std::io::BufReader::new(stdout);
                    let mut line = Vec::new();
                    let mut truncated = false;
                    loop {
                        let line_truncated =
                            match read_stage_line(&mut reader, &mut line, MAX_STAGE_LINE_BYTES) {
                                Ok(Some(truncated)) => truncated,
                                Ok(None) | Err(_) => break,
                            };
                        let line_text = String::from_utf8_lossy(&line);
                        if !line_truncated {
                            if let Some(snapshot) = parse_stage_marker(line_text.trim()) {
                                if let Ok(mut cell) = stage_progress_cell().lock() {
                                    let merged = merge_stage_snapshot(&cell, snapshot);
                                    *cell = merged;
                                }
                                if let Ok(mut last_activity) = progress_activity.lock() {
                                    *last_activity = std::time::Instant::now();
                                }
                                continue;
                            }
                        }
                        if collected_out.len() < MAX_STAGE_CAPTURE_BYTES {
                            let room = MAX_STAGE_CAPTURE_BYTES - collected_out.len();
                            collected_out.extend_from_slice(&line[..line.len().min(room)]);
                        } else if !truncated {
                            collected_out.extend_from_slice(b"\n...[truncated]");
                            truncated = true;
                        }
                    }
                    let _ = tx.send(collected_out);
                });
                rx
            });
            // Mirror run_bounded_command_cancel: poll for exit, kill the
            // whole process group on cancel or timeout.
            let started = std::time::Instant::now();
            let mut last_heartbeat = started;
            let outcome = loop {
                match child.try_wait() {
                    Ok(Some(status)) => break Ok(status),
                    Ok(None) => {
                        let quiet_for = progress_activity
                            .lock()
                            .map(|last| last.elapsed())
                            .unwrap_or_default();
                        if quiet_for >= STAGE_PROGRESS_HEARTBEAT
                            && last_heartbeat.elapsed() >= STAGE_PROGRESS_HEARTBEAT
                        {
                            if let Ok(mut snapshot) = stage_progress_cell().lock() {
                                if snapshot.active {
                                    snapshot.detail = match snapshot.phase.as_str() {
                                        "install" => "Installing the staged image. This can take several minutes…".into(),
                                        "verify" => "Verifying the staged image and checking its safety policy…".into(),
                                        "finalize" => "Preparing the staged deployment for the next boot…".into(),
                                        "download" => "The image download is still running. Waiting for the next layer update…".into(),
                                        _ => "Preparing the update and checking system readiness…".into(),
                                    };
                                }
                            }
                            if let Ok(mut last_activity) = progress_activity.lock() {
                                *last_activity = std::time::Instant::now();
                            }
                            last_heartbeat = std::time::Instant::now();
                        }
                    }
                    Err(error) => break Err(error),
                }
                if cancel.load(std::sync::atomic::Ordering::Relaxed) {
                    kyth_shared::system::process::kill_process_group(&mut child);
                    // Reap the killed child: killpg alone leaves a
                    // zombie whose exit status nobody collects.
                    let _ = child.wait();
                    break Err(std::io::Error::new(
                        std::io::ErrorKind::Interrupted,
                        "command was cancelled",
                    ));
                }
                if started.elapsed() > timeout {
                    kyth_shared::system::process::kill_process_group(&mut child);
                    // Reap the killed child: killpg alone leaves a
                    // zombie whose exit status nobody collects.
                    let _ = child.wait();
                    break Err(std::io::Error::new(
                        std::io::ErrorKind::TimedOut,
                        "command timed out",
                    ));
                }
                std::thread::sleep(Duration::from_millis(25));
            };
            // Pipes close on exit/kill, so both readers normally
            // deliver at once; the bounded join covers a grandchild
            // that escaped the group kill and is holding a pipe open.
            let collected_out = join_stage_reader(stdout_rx);
            let collected_err = join_stage_reader(stderr_rx);
            match outcome {
                Ok(status) => {
                    let mut detail = String::from_utf8_lossy(&collected_out).trim().to_string();
                    let stderr = String::from_utf8_lossy(&collected_err).trim().to_string();
                    if !stderr.is_empty() {
                        if !detail.is_empty() {
                            detail.push('\n');
                        }
                        detail.push_str(&stderr);
                    }
                    let detail: String = kyth_shared::system::process::redact_sensitive_text(
                        kyth_shared::system::process::strip_ansi(&detail).as_str(),
                    )
                    .chars()
                    .rev()
                    .take(1200)
                    .collect::<String>()
                    .chars()
                    .rev()
                    .collect();
                    let state = if status.success() {
                        "complete"
                    } else {
                        "failed"
                    };
                    let detail = if detail.is_empty() {
                        if status.success() {
                            format!("{operation_for_thread} complete.")
                        } else {
                            format!(
                                "{operation_for_thread} failed (exit code {}).",
                                status.code().unwrap_or(-1)
                            )
                        }
                    } else {
                        detail
                    };
                    (state.to_string(), detail)
                }
                Err(error) => (
                    "failed".to_string(),
                    format!("{operation_for_thread} could not complete: {error}"),
                ),
            }
        }
        Err(error) => (
            "failed".to_string(),
            format!("{operation_for_thread} could not start: {error}"),
        ),
    };
    if let Ok(mut snapshot) = stage_progress_cell().lock() {
        snapshot.active = false;
    }
    update_jobs().finish(job, &state, detail);
}

/// Stage variant of `start_update_job` that streams the helper's stdout so
/// progress markers update the Updates page live. Cancel, timeout, and
/// terminal detail behave exactly like the non-streaming path.
fn start_stage_job(
    job_slug: &str,
    operation: &str,
    argv: Vec<String>,
    timeout: Duration,
    slot: MutatingSlot,
) -> Result<UpdateActionLaunch, String> {
    kyth_shared::commands::normalize_command(&argv)
        .map_err(|_| "update produced an invalid command".to_string())?;
    let job = format!(
        "update-{}-{}",
        job_slug,
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    let (job, cancel) = update_jobs().start(&job, format!("{operation} is running…"));
    if let Ok(mut snapshot) = stage_progress_cell().lock() {
        *snapshot = StageProgressSnapshot {
            pct: 0,
            phase: "prepare".into(),
            detail: "Starting the secure update helper and checking system readiness…".into(),
            active: true,
        };
    }
    let job_for_thread = job.clone();
    let operation_for_thread = operation.to_string();
    let thread = std::thread::Builder::new().spawn(move || {
        // Held to the end of the job: the second mutating launch fails at
        // take_mutating_slot instead of racing this one.
        let _slot = slot;
        // Declared after the slot so it drops FIRST: the snapshot reads
        // inactive before the slot frees the next stage launch.
        let _progress_guard = StageProgressGuard;
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            run_stage_worker(&job_for_thread, &operation_for_thread, argv, timeout, cancel);
        }));
        if result.is_err() {
            update_jobs().finish(
                &job_for_thread,
                "failed",
                format!(
                    "{operation_for_thread} could not complete: the update worker stopped unexpectedly."
                ),
            );
        }
    });
    match thread {
        Ok(_) => Ok(UpdateActionLaunch {
            job,
            state: "running".into(),
            detail: format!("{operation} is running…"),
        }),
        Err(error) => {
            // A failed spawn drops the closure — and with it the
            // mutating slot — but the job entry and the progress
            // snapshot were already published; resolve both here so
            // neither is left claiming work that never started.
            if let Ok(mut snapshot) = stage_progress_cell().lock() {
                snapshot.active = false;
            }
            let detail = format!("{operation} could not start: {error}");
            update_jobs().finish(&job, "failed", detail.clone());
            Err(detail)
        }
    }
}

#[derive(Serialize)]
pub(crate) struct JustRecipeResponse {
    pub(crate) name: String,
    pub(crate) params: String,
    pub(crate) comment: String,
}

#[tauri::command]
pub(crate) async fn just_list() -> Vec<JustRecipeResponse> {
    // P6: `just --list` is bounded at 10 s; keep it off the async workers.
    tauri::async_runtime::spawn_blocking(|| {
        kyth_shared::system::just::just_list()
            .into_iter()
            .map(|recipe| JustRecipeResponse {
                name: recipe.name,
                params: recipe.params,
                comment: recipe.comment,
            })
            .collect::<Vec<_>>()
    })
    .await
    .unwrap_or_default()
}

fn just_output_detail(recipe: &str, output: &std::process::Output) -> String {
    let mut text = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr);
    if !stderr.trim().is_empty() {
        if !text.is_empty() {
            text.push('\n');
        }
        text.push_str(&stderr);
    }
    let text = kyth_shared::system::process::redact_sensitive_text(
        kyth_shared::system::process::strip_ansi(text.trim()).as_str(),
    );
    let detail: String = text
        .chars()
        .rev()
        .take(800)
        .collect::<String>()
        .chars()
        .rev()
        .collect();
    if !detail.trim().is_empty() {
        return if output.status.success() {
            format!("{recipe} complete — {}", detail.trim())
        } else {
            format!("{recipe} could not be completed — {}", detail.trim())
        };
    }
    if output.status.success() {
        format!("{recipe} complete.")
    } else {
        match output.status.code() {
            Some(code) => format!("{recipe} could not be completed (exit code {code})."),
            None => format!("{recipe} stopped before it could complete."),
        }
    }
}

#[derive(Serialize)]
pub(crate) struct HubActionLaunch {
    pub(crate) job: String,
    pub(crate) state: String,
    pub(crate) detail: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub(crate) enum HubAction {
    SetupTailscale,
    UpdateHealth,
    ResumeCheck,
    DeviceInfo,
    StartupApps,
    FirmwareUpdate,
    HealthCheck,
    GamingStackStatus,
    FixDualbootClock,
    SetupBootWindowsSteam,
    ReclaimWindows,
    InstallLudusavi,
    InstallMsFonts,
    SetupKythDevBox,
    AiDevStatus,
    AiDevSetup,
    SetupWaydroid,
    RemoveWaydroid,
    InstallVscode,
    InstallBoxbuddy,
    InstallJetbrainsToolbox,
    GamingMode,
    BalancedMode,
    HdrPerGame,
    EnableBpftune,
    DisableBpftune,
    InstallSteam,
    InstallHeroic,
    InstallLutris,
    InstallBottles,
    InstallPrismlauncher,
    InstallItch,
    InstallEpicLauncher,
    InstallBattlenet,
    InstallEaApp,
    InstallUbisoftConnect,
    PreheatShaders,
    EnableObsCapture,
    GameBoost,
    ControllerCheck,
    ExportSteamGames,
    InstallObs,
    InstallGpuScreenRecorder,
    InstallGoverlay,
    InstallMangojuice,
    InstallUmu,
    InstallLact,
    InstallPiper,
    InstallSolaar,
    NvidiaStatus,
    ListPresets,
    SetupPrinter,
    EnrollSecureboot,
    SystemAudit,
    GamingAudit,
}

impl HubAction {
    fn recipe(&self) -> &'static str {
        match self {
            Self::SetupTailscale => "setup-tailscale",
            Self::UpdateHealth => "update-health",
            Self::ResumeCheck => "resume-check",
            Self::DeviceInfo => "device-info",
            Self::StartupApps => "startup-apps",
            Self::FirmwareUpdate => "firmware-update",
            Self::HealthCheck => "health-check",
            Self::GamingStackStatus => "gaming-stack-status",
            Self::FixDualbootClock => "fix-dualboot-clock",
            Self::SetupBootWindowsSteam => "setup-boot-windows-steam",
            Self::ReclaimWindows => "reclaim-windows",
            Self::InstallLudusavi => "install-ludusavi",
            Self::InstallMsFonts => "install-ms-fonts",
            Self::SetupKythDevBox => "setup-kyth-dev-box",
            Self::AiDevStatus => "ai-dev-status",
            Self::AiDevSetup => "ai-dev-setup",
            Self::SetupWaydroid => "setup-waydroid",
            // The Hub confirms first (RecipeButton confirm), so it runs the
            // prompt-free variant; the interactive recipe stays for terminals.
            Self::RemoveWaydroid => "remove-waydroid-confirmed",
            Self::InstallVscode => "install-vscode",
            Self::InstallBoxbuddy => "install-boxbuddy",
            Self::InstallJetbrainsToolbox => "install-jetbrains-toolbox",
            Self::GamingMode => "gaming-mode",
            Self::BalancedMode => "balanced-mode",
            Self::HdrPerGame => "hdr-per-game",
            Self::EnableBpftune => "enable-bpftune",
            Self::DisableBpftune => "disable-bpftune",
            Self::InstallSteam => "install-steam",
            Self::InstallHeroic => "install-heroic",
            Self::InstallLutris => "install-lutris",
            Self::InstallBottles => "install-bottles",
            Self::InstallPrismlauncher => "install-prismlauncher",
            Self::InstallItch => "install-itch",
            Self::InstallEpicLauncher => "install-epic-launcher",
            Self::InstallBattlenet => "install-battlenet",
            Self::InstallEaApp => "install-ea-app",
            Self::InstallUbisoftConnect => "install-ubisoft-connect",
            Self::PreheatShaders => "preheat-shaders",
            Self::EnableObsCapture => "enable-obs-capture",
            Self::GameBoost => "game-boost",
            Self::ControllerCheck => "controller-check",
            Self::ExportSteamGames => "export-steam-games",
            Self::InstallObs => "install-obs",
            Self::InstallGpuScreenRecorder => "install-gpu-screen-recorder",
            Self::InstallGoverlay => "install-goverlay",
            Self::InstallMangojuice => "install-mangojuice",
            Self::InstallUmu => "install-umu",
            Self::InstallLact => "install-lact",
            Self::InstallPiper => "install-piper",
            Self::InstallSolaar => "install-solaar",
            Self::NvidiaStatus => "nvidia-status",
            Self::ListPresets => "list-presets",
            Self::SetupPrinter => "setup-printer",
            Self::EnrollSecureboot => "enroll-secureboot",
            Self::SystemAudit => "system-audit",
            Self::GamingAudit => "gaming-audit",
        }
    }

    /// Whether running this recipe only reads or reports state: status,
    /// audit, and check listings, plus the autostart settings opener
    /// (which changes nothing itself). Everything not listed here is
    /// treated as MUTATING — installs, firmware updates, mode switches,
    /// enrollments — so an unclassified future variant fails safe
    /// (serialized) rather than racing. `run_hub_action` serializes
    /// mutating recipes behind the backend hub-action slot and lets
    /// read-only ones run without it, so a long install never blocks a
    /// status read.
    fn is_read_only(&self) -> bool {
        matches!(
            self,
            Self::UpdateHealth
                | Self::ResumeCheck
                | Self::DeviceInfo
                | Self::StartupApps
                | Self::HealthCheck
                | Self::GamingStackStatus
                | Self::AiDevStatus
                | Self::NvidiaStatus
                | Self::ListPresets
                | Self::ControllerCheck
                | Self::SystemAudit
                | Self::GamingAudit
        )
    }
}

fn start_hub_action_job(action: HubAction) -> Result<HubActionLaunch, String> {
    let recipe = action.recipe();
    let argv = kyth_shared::system::just::command_for(recipe, &[])
        .ok_or_else(|| "Hub action is not allowlisted".to_string())?;
    kyth_shared::commands::normalize_command(&argv)
        .map_err(|_| "recipe produced an invalid command".to_string())?;
    // Backend single-flight for mutating recipes (B-H1): without it, two
    // recipes run at once — stacked sudo prompts, racing writes to the
    // same system state, and cross-races with the Updates page's own
    // serialization (a hub-action firmware update beside a bootc stage).
    // Read-only recipes skip the slot so a long install never blocks a
    // status read. Claimed BEFORE the job exists; the guard moves into
    // the worker so it is held for the job's whole life.
    let slot = if action.is_read_only() {
        None
    } else {
        Some(super::job::take_hub_action_slot()?)
    };
    let job = format!(
        "hub-action-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    let (job, cancel) = hub_action_jobs().start(&job, format!("Running {recipe}…"));
    let job_for_thread = job.clone();
    let recipe_for_thread = recipe.to_string();
    let thread = std::thread::Builder::new().spawn(move || {
        // Held to the end of the job: the next mutating launch fails at
        // take_hub_action_slot instead of racing this one.
        let _slot = slot;
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let mut command = Command::new(&argv[0]);
            command.args(&argv[1..]);
            let inherited = std::env::vars().collect::<std::collections::BTreeMap<_, _>>();
            let sanitized = kyth_shared::commands::environment_for(
                kyth_shared::commands::EnvironmentPolicy::Sanitized,
                &inherited,
            );
            command.env_clear().envs(sanitized);
            kyth_shared::system::just::configure_command(&mut command);
            if std::path::Path::new("/usr/bin/ksshaskpass").exists() {
                command.env("SUDO_ASKPASS", "/usr/bin/ksshaskpass");
            }
            let result = kyth_shared::system::process::run_bounded_command_cancel(
                command,
                timeout_for(JobTimeoutClass::HubAction),
                &cancel,
            );
            match result {
                Ok(output) => {
                    let state = if output.status.success() {
                        "complete"
                    } else {
                        "failed"
                    };
                    (
                        state.to_string(),
                        just_output_detail(&recipe_for_thread, &output),
                    )
                }
                Err(error) => (
                    "failed".to_string(),
                    format!("Could not start {recipe_for_thread}: {error}"),
                ),
            }
        }));
        let (state, detail) = result.unwrap_or_else(|_| {
            (
                "failed".to_string(),
                format!(
                    "Could not complete {recipe_for_thread}: the Hub action worker stopped unexpectedly."
                ),
            )
        });
        hub_action_jobs().finish(&job_for_thread, &state, detail);
    });
    match thread {
        Ok(_) => Ok(HubActionLaunch {
            job,
            state: "running".into(),
            detail: format!("Running {recipe}…"),
        }),
        Err(error) => {
            // A failed spawn drops the closure — and with it the
            // hub-action slot — but the job entry was already
            // published; resolve it here so it is not left claiming
            // work that never started.
            let detail = format!("Could not start {recipe}: {error}");
            hub_action_jobs().finish(&job, "failed", detail.clone());
            Err(detail)
        }
    }
}

/// Start an Updates-page operation as a native Rust-managed job. The command
/// is always a fixed argv; `just` is intentionally not involved here. The
/// privileged safety helper remains the root boundary for upgrade policy and
/// boot-health recording, while Rust owns lifecycle, timeout, and UI output.
#[derive(Serialize)]
pub(crate) struct UpdateActionLaunch {
    pub(crate) job: String,
    pub(crate) state: String,
    pub(crate) detail: String,
}

fn start_update_job(
    job_slug: &str,
    operation: &str,
    argv: Vec<String>,
    timeout: Duration,
    slot: MutatingSlot,
) -> Result<UpdateActionLaunch, String> {
    kyth_shared::commands::normalize_command(&argv)
        .map_err(|_| "update produced an invalid command".to_string())?;
    // The slug (not the display label) owns the id: frontend reattach only
    // trusts `<prefix>-<nanos>` ids, so a label with spaces would strand the
    // job (and its Cancel) across a reload.
    let job = format!(
        "update-{}-{}",
        job_slug,
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    let (job, cancel) = update_jobs().start(&job, format!("{operation} is running…"));
    let job_for_thread = job.clone();
    let operation_for_thread = operation.to_string();
    let thread = std::thread::Builder::new().spawn(move || {
        // Held to the end of the job: the second mutating launch fails at
        // take_mutating_slot instead of racing this one.
        let _slot = slot;
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let mut command = Command::new(&argv[0]);
            command.args(&argv[1..]);
            let inherited = std::env::vars().collect::<std::collections::BTreeMap<_, _>>();
            let desktop = kyth_shared::commands::environment_for(
                kyth_shared::commands::EnvironmentPolicy::Desktop,
                &inherited,
            );
            command.env_clear().envs(desktop);
            if std::path::Path::new("/usr/bin/ksshaskpass").exists() {
                command.env("SUDO_ASKPASS", "/usr/bin/ksshaskpass");
            }
            let result =
                kyth_shared::system::process::run_bounded_command_cancel(command, timeout, &cancel);
            let (state, detail) = match result {
                Ok(output) => {
                    let mut detail = String::from_utf8_lossy(&output.stdout).trim().to_string();
                    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
                    if !stderr.is_empty() {
                        if !detail.is_empty() {
                            detail.push('\n');
                        }
                        detail.push_str(&stderr);
                    }
                    let detail: String = kyth_shared::system::process::redact_sensitive_text(
                        kyth_shared::system::process::strip_ansi(&detail).as_str(),
                    )
                    .chars()
                    .rev()
                    .take(1200)
                    .collect::<String>()
                    .chars()
                    .rev()
                    .collect();
                    let state = if output.status.success() {
                        "complete"
                    } else {
                        "failed"
                    };
                    let detail = if detail.is_empty() {
                        if output.status.success() {
                            format!("{operation_for_thread} complete.")
                        } else {
                            format!(
                                "{operation_for_thread} failed (exit code {}).",
                                output.status.code().unwrap_or(-1)
                            )
                        }
                    } else {
                        detail
                    };
                    (state.to_string(), detail)
                }
                Err(error) => (
                    "failed".to_string(),
                    format!("{operation_for_thread} could not complete: {error}"),
                ),
            };
            (state, detail)
        }));
        let (state, detail) = result.unwrap_or_else(|_| {
            (
                "failed".to_string(),
                format!(
                    "{operation_for_thread} could not complete: the update worker stopped unexpectedly."
                ),
            )
        });
        update_jobs().finish(&job_for_thread, &state, detail);
    });
    match thread {
        Ok(_) => Ok(UpdateActionLaunch {
            job,
            state: "running".into(),
            detail: format!("{operation} is running…"),
        }),
        Err(error) => {
            // A failed spawn drops the closure — and with it the
            // mutating slot — but the job entry was already
            // published; resolve it here so it is not left claiming
            // work that never started.
            let detail = format!("{operation} could not start: {error}");
            update_jobs().finish(&job, "failed", detail.clone());
            Err(detail)
        }
    }
}

#[tauri::command]
pub(crate) fn run_hub_action(action: HubAction) -> Result<HubActionLaunch, String> {
    start_hub_action_job(action)
}

fn update_store_status(store: &JobStore, job: String, not_found: &str) -> crate::InstallStatus {
    let (state, detail) = store.status(&job).unwrap_or((
        kyth_shared::system::jobs::STATE_UNKNOWN.into(),
        not_found.into(),
    ));
    crate::InstallStatus {
        id: job,
        state,
        detail,
    }
}

#[tauri::command]
pub(crate) fn hub_action_status(job: String) -> crate::InstallStatus {
    update_store_status(hub_action_jobs(), job, "Hub action job not found.")
}

/// Cancel a running Hub action: its recipe process is killed within one
/// poll tick and the job reads `cancelled` from then on.
#[tauri::command]
pub(crate) fn hub_action_cancel(job: String) -> crate::InstallStatus {
    hub_action_jobs().cancel(&job);
    update_store_status(hub_action_jobs(), job, "Hub action job not found.")
}

#[tauri::command]
pub(crate) fn bootc_upgrade() -> Result<UpdateActionLaunch, String> {
    require_binary(
        "/usr/bin/kyth-safe-upgrade",
        "The native KythOS update helper is not installed on this system.",
    )?;
    // No lock check here on purpose: the Hub shell runs as the user and
    // /run/kyth-bootc.lock is root-only, so opening it here fails with
    // EACCES before any update can start. Serialization is the slot above
    // (no stacked sudo prompts from this Hub) plus the flock that
    // kyth-safe-upgrade holds for the whole stage.
    let slot = take_mutating_slot()?;
    start_stage_job(
        "stage",
        "Download and stage",
        vec!["sudo", "-A", "/usr/bin/kyth-safe-upgrade"]
            .into_iter()
            .map(String::from)
            .collect(),
        timeout_for(JobTimeoutClass::LongTransfer),
        slot,
    )
}

#[tauri::command]
pub(crate) fn bootc_rollback() -> Result<UpdateActionLaunch, String> {
    require_binary("/usr/bin/bootc", "bootc is not installed on this system.")?;
    // No lock check here on purpose (see bootc_upgrade): the Hub shell
    // runs as the user and cannot open the root-only lock file. Unlike
    // stage/switch, rollback has no helper and takes no flock — it runs
    // `bootc rollback` directly, so cross-process serialization rests
    // on bootc/ostree's internal sysroot lock (a second concurrent
    // writer is refused) plus the slot above within this Hub.
    let slot = take_mutating_slot()?;
    start_update_job(
        "rollback",
        "Rollback",
        vec!["sudo", "-A", "/usr/bin/bootc", "rollback"]
            .into_iter()
            .map(String::from)
            .collect(),
        timeout_for(JobTimeoutClass::UpdateMutating),
        slot,
    )
}

#[tauri::command]
pub(crate) fn bootc_switch_branch(branch: String) -> Result<UpdateActionLaunch, String> {
    require_binary(
        "/usr/bin/kyth-bootc-guard",
        "The KythOS bootc guard helper is not installed on this system.",
    )?;
    let channel = kyth_shared::system::bootc_policy::switch_channel_arg(&branch)
        .ok_or_else(|| "unknown channel".to_string())?;
    let operation = format!(
        "switch-{}",
        if channel == "stable" {
            "latest"
        } else {
            channel
        }
    );
    let mut argv = vec!["sudo", "-A", "/usr/bin/kyth-bootc-guard"]
        .into_iter()
        .map(String::from)
        .collect::<Vec<_>>();
    argv.push(operation);
    // No in-process lock check — the Hub shell cannot open the root-only
    // lock file. kyth-bootc-guard holds the bootc flock for the whole
    // switch, but that flock only excludes other flock holders; against
    // direct `bootc` callers (rollback above) the final serializer is
    // bootc/ostree's internal sysroot lock.
    let slot = take_mutating_slot()?;
    // LongTransfer (3600s), not the 300s download-free tier: switching
    // to a channel whose image is not already cached pulls it — the
    // same download staging performs — so the short tier killed
    // legitimate switches mid-pull on slow links.
    start_update_job(
        "switch",
        "Switch channel",
        argv,
        timeout_for(JobTimeoutClass::LongTransfer),
        slot,
    )
}

#[tauri::command]
pub(crate) fn apply_staged() -> Result<UpdateActionLaunch, String> {
    require_binary(
        "/usr/libexec/kyth-finalize-staged",
        "The staged-update finalizer is not installed on this system.",
    )?;
    // No in-process lock check (see bootc_upgrade): the slot above keeps
    // the restart from racing an upgrade/switch launched from this Hub.
    let slot = take_mutating_slot()?;
    start_update_job(
        "apply",
        "Restart to apply staged update",
        vec!["sudo", "-A", "/usr/libexec/kyth-finalize-staged", "reboot"]
            .into_iter()
            .map(String::from)
            .collect(),
        timeout_for(JobTimeoutClass::UpdateMutating),
        slot,
    )
}

#[tauri::command]
pub(crate) fn update_job_status(job: String) -> crate::InstallStatus {
    update_store_status(update_jobs(), job, "Update job not found.")
}

/// Cancel a running update job: its process is killed within one poll tick
/// and the job reads `cancelled` from then on.
#[tauri::command]
pub(crate) fn update_job_cancel(job: String) -> crate::InstallStatus {
    update_jobs().cancel(&job);
    update_store_status(update_jobs(), job, "Update job not found.")
}

#[tauri::command]
pub(crate) fn branch_display_name(tag: Option<String>) -> String {
    kyth_shared::system::bootc_policy::branch_display_name(tag.as_deref())
}

#[tauri::command]
pub(crate) async fn pending_updates_summary() -> std::collections::HashMap<String, String> {
    tauri::async_runtime::spawn_blocking(
        kyth_shared::system::updates_unified::pending_updates_summary,
    )
    .await
    .unwrap_or_default()
}

#[tauri::command]
pub(crate) async fn update_status() -> UpdateStatusResponse {
    tauri::async_runtime::spawn_blocking(update_status_response)
        .await
        .unwrap_or_else(|_| UpdateStatusResponse {
            booted: None,
            staged: false,
            rollback: false,
            remote_digest: None,
            blocked_reason: Some("Could not read update status.".to_string()),
            retry_cmd: Some("bootc upgrade --check".to_string()),
            check_state: "error".to_string(),
            detail: "Could not read update status.".to_string(),
        })
}

fn update_status_response() -> UpdateStatusResponse {
    let status = kyth_shared::system::update_status::check_update_status();
    UpdateStatusResponse {
        booted: status.booted,
        staged: status.staged,
        rollback: status.rollback,
        remote_digest: status.remote_digest,
        blocked_reason: status.blocked_reason,
        retry_cmd: status.retry_cmd,
        check_state: status.check_state,
        detail: status.detail,
    }
}

#[derive(Serialize)]
pub(crate) struct UpdateStatusResponse {
    pub(crate) booted: Option<String>,
    pub(crate) staged: bool,
    pub(crate) rollback: bool,
    pub(crate) remote_digest: Option<String>,
    pub(crate) blocked_reason: Option<String>,
    pub(crate) retry_cmd: Option<String>,
    pub(crate) check_state: String,
    pub(crate) detail: String,
}

#[derive(Serialize)]
pub(crate) struct AvailabilityStatusResponse {
    pub(crate) state: String,
    pub(crate) detail: String,
    pub(crate) flatpak_count: i32,
    pub(crate) flatpak_detail: String,
    pub(crate) staged: bool,
    pub(crate) manifest_raw: String,
    pub(crate) blocked_reason: String,
}

#[tauri::command]
pub(crate) async fn collect_availability(use_cached: Option<bool>) -> AvailabilityStatusResponse {
    let status = tauri::async_runtime::spawn_blocking(move || {
        kyth_shared::system::update_availability::collect_availability(use_cached.unwrap_or(true))
    })
    .await
    .unwrap_or_else(
        |_| kyth_shared::system::update_availability::AvailabilityStatus {
            state: "error".to_string(),
            detail: "Could not check update availability.".to_string(),
            flatpak_count: 0,
            flatpak_detail: String::new(),
            staged: false,
            manifest_raw: String::new(),
            blocked_reason: "Could not check update availability.".to_string(),
        },
    );
    AvailabilityStatusResponse {
        state: status.state,
        detail: status.detail,
        flatpak_count: status.flatpak_count,
        flatpak_detail: status.flatpak_detail,
        staged: status.staged,
        manifest_raw: status.manifest_raw,
        blocked_reason: status.blocked_reason,
    }
}

/// Resolve the active channel without making the short-lived probe cache a
/// hard dependency. The fallback can query bootc, so keep it off the Tauri
/// command/UI thread just like the update probes above.
#[tauri::command]
pub(crate) async fn current_update_channel() -> Option<String> {
    tauri::async_runtime::spawn_blocking(kyth_shared::system::bootc::current_branch)
        .await
        .ok()
        .flatten()
}

#[derive(Serialize)]
pub(crate) struct UpdateHealthResponse {
    pub(crate) status: String,
    pub(crate) pending_digest: String,
    pub(crate) last_healthy_digest: String,
    pub(crate) failures: i64,
    pub(crate) quarantined: usize,
    pub(crate) detail: String,
}

fn native_health_fallback() -> Option<(String, String, String, i64)> {
    // Prefer the same disk cache used by the rest of the Hub, but recover on
    // systems whose probe service has not populated it yet. This is still a
    // bounded native read and runs inside update_health's blocking worker.
    let status_data = kyth_shared::system::probe::read_section("bootc-status-data")
        .or_else(kyth_shared::system::bootc_query::fetch_status_data)?;
    let digest = kyth_shared::system::registry::booted_image_digest(&status_data)?;
    let os_release = std::fs::read_to_string("/usr/lib/os-release")
        .or_else(|_| std::fs::read_to_string("/etc/os-release"))
        .ok()?;
    let identity_ok = os_release
        .lines()
        .any(|line| line.trim() == "ID=kythos" || line.trim() == "ID=\"kythos\"");
    let runtime = kyth_shared::system::boot_runtime::boot_runtime_checks_with_deadline(
        std::time::Duration::from_secs(5),
        std::time::Duration::from_millis(100),
    );
    let mut failures = runtime
        .iter()
        .filter(|check| !check.passed)
        .map(|check| format!("{}: {}", check.name, check.detail))
        .collect::<Vec<_>>();
    if !identity_ok {
        failures.push("KythOS identity: /usr/lib/os-release is not ID=kythos".to_string());
    }
    if failures.is_empty() {
        Some((
            "healthy".to_string(),
            format!("Native boot checks passed for {digest}; no persistent boot-health record was available."),
            digest,
            0,
        ))
    } else {
        let count = failures.len() as i64;
        Some((
            "unhealthy".to_string(),
            format!("Native boot checks failed: {}", failures.join("; ")),
            digest,
            count,
        ))
    }
}

fn update_health_response() -> UpdateHealthResponse {
    let state = kyth_shared::system::boot_health::read_default_state();
    if state.status == "unknown"
        && state.current_digest.is_empty()
        && state.last_healthy_digest.is_empty()
        && state.updated_at == 0
    {
        if let Some((status, detail, digest, failures)) = native_health_fallback() {
            // The live booted digest is the digest under evaluation
            // (pending), not a known-good one: only a passing native
            // check may claim it as last-healthy, and the failure count
            // is the failed native checks — not the empty record's zero.
            let last_healthy_digest = if status == "healthy" {
                digest.clone()
            } else {
                String::new()
            };
            return UpdateHealthResponse {
                status,
                pending_digest: digest,
                last_healthy_digest,
                failures,
                quarantined: state.quarantined.len(),
                detail,
            };
        }
    }
    let invariants = state.invariants();
    let detail = if invariants.is_empty() {
        if state.status == "unknown" {
            "Boot health has not been recorded yet; native checks could not establish a live result.".to_string()
        } else {
            format!(
                "Boot health is {} · {} quarantined digest(s).",
                state.status,
                state.quarantined.len()
            )
        }
    } else {
        format!(
            "Boot health state needs attention: {}",
            invariants.join(", ")
        )
    };
    UpdateHealthResponse {
        status: state.status,
        pending_digest: state.pending_digest,
        last_healthy_digest: state.last_healthy_digest,
        failures: state.failures,
        quarantined: state.quarantined.len(),
        detail,
    }
}

#[tauri::command]
pub(crate) async fn update_health() -> UpdateHealthResponse {
    tauri::async_runtime::spawn_blocking(update_health_response)
        .await
        .unwrap_or_else(|_| UpdateHealthResponse {
            status: "unknown".to_string(),
            pending_digest: String::new(),
            last_healthy_digest: String::new(),
            failures: 0,
            quarantined: 0,
            detail: "Native boot-health check could not complete.".to_string(),
        })
}

#[cfg(test)]
mod tests {
    use super::{HubAction, *};

    static SLOT_TEST_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

    #[test]
    fn hub_action_deserializes_allowlisted_recipe() {
        let action: HubAction =
            serde_json::from_str("\"enroll-secureboot\"").expect("known action");
        assert_eq!(action.recipe(), "enroll-secureboot");
    }

    #[test]
    fn hub_action_rejects_unknown_recipe() {
        let result = serde_json::from_str::<HubAction>("\"run-arbitrary-command\"");
        assert!(result.is_err());
    }

    #[test]
    fn stage_marker_parses_pct_phase_and_detail() {
        let snapshot = super::parse_stage_marker(
            "KYTH_STAGE_PROGRESS pct=42 phase=download detail=Downloading layer 12 of 39",
        )
        .expect("marker parses");
        assert_eq!(snapshot.pct, 42);
        assert_eq!(snapshot.phase, "download");
        assert_eq!(snapshot.detail, "Downloading layer 12 of 39");
        assert!(snapshot.active);
    }

    #[test]
    fn stage_marker_rejects_non_markers_and_caps_pct() {
        assert!(super::parse_stage_marker("Downloading layer 12 of 39").is_none());
        let snapshot = super::parse_stage_marker("KYTH_STAGE_PROGRESS pct=200 phase=install")
            .expect("marker parses");
        assert_eq!(snapshot.pct, 99);
        assert_eq!(snapshot.detail, "Installing the staged image…");
    }

    #[test]
    fn update_release_summary_matches_channel_and_exact_image_digest() {
        let digest = format!("sha256:{}", "a".repeat(64));
        let body = format!(
            "# Kyth image\n\nImage: `ghcr.io/kyth-os/kyth@{digest}`\n\n### Major Package Changes\n| | Name | Previous | New |\n| --- | --- | --- | --- |\n| ~ | `gamescope` | 3.16.28-1 | 3.16.29-1 |\n| + | `mesa-extra` |  | 1.0-1 |\n\n### Security fixes\n| CVE | Package |\n| --- | --- |\n| [CVE-2026-12345](https://nvd.nist.gov/vuln/detail/CVE-2026-12345) | `kernel` |\n"
        );
        let payload = serde_json::json!([{
            "tag_name": "image-testing-20260925-2481-1-8b81dca7",
            "draft": false,
            "prerelease": true,
            "body": body,
        }]);
        let summary =
            super::update_release_summary_from_api(&payload.to_string(), "testing", &digest)
                .expect("matching published image release");
        assert_eq!(summary.version, "testing.20260925.2481.1.8b81dca7");
        assert_eq!(
            summary.release_url,
            "https://github.com/kyth-os/kyth/releases/tag/image-testing-20260925-2481-1-8b81dca7"
        );
        assert_eq!(summary.highlights_title, "Package changes");
        assert_eq!(summary.flavor, "fedora");
        assert_eq!(summary.package_total, 2);
        assert!(summary
            .highlights
            .contains(&"Updated gamescope from 3.16.28-1 to 3.16.29-1".to_string()));
        assert!(summary
            .highlights
            .contains(&"Added mesa-extra 1.0-1".to_string()));
        assert!(summary
            .highlights
            .contains(&"Security fix: CVE-2026-12345".to_string()));
    }

    #[test]
    fn normalize_image_branch_maps_channels_and_flavors() {
        assert_eq!(
            super::normalize_image_branch("testing"),
            Some(("testing", "fedora"))
        );
        assert_eq!(
            super::normalize_image_branch("latest"),
            Some(("latest", "fedora"))
        );
        assert_eq!(
            super::normalize_image_branch("testing-cachy"),
            Some(("testing", "cachy"))
        );
        assert_eq!(
            super::normalize_image_branch("latest-cachy"),
            Some(("latest", "cachy"))
        );
        assert_eq!(super::normalize_image_branch("bogus"), None);
        assert_eq!(super::normalize_image_branch("testing-cachy-extra"), None);
        assert_eq!(super::normalize_image_branch(""), None);
    }

    #[test]
    fn update_release_summary_matches_cachy_release_on_base_channel() {
        let digest = format!("sha256:{}", "c".repeat(64));
        let body = format!(
            "# Kyth image\n\nImage: `ghcr.io/kyth-os/kyth@{digest}`\n\n### All RPM Changes\n| | Name | Previous | New |\n| --- | --- | --- | --- |\n| ~ | `kernel-cachyos` | 6.12.0-1 | 6.13.0-1 |\n"
        );
        let payload = serde_json::json!([{
            "tag_name": "image-testing-cachy-20261013-2735-1-27a537a0",
            "draft": false,
            "prerelease": true,
            "body": body,
        }]);
        let summary =
            super::update_release_summary_from_api(&payload.to_string(), "testing", &digest)
                .expect("matching published cachy image release");
        assert_eq!(summary.version, "testing.20261013.2735.1.27a537a0");
        assert_eq!(summary.flavor, "cachy");
        assert_eq!(summary.package_total, 1);
        assert!(summary
            .highlights
            .contains(&"Updated kernel-cachyos from 6.12.0-1 to 6.13.0-1".to_string()));
    }

    #[test]
    fn release_highlights_return_the_complete_package_list() {
        let rows: Vec<String> = (0..8)
            .map(|index| format!("| ~ | `pkg{index:02}` | 1.0-{index} | 1.1-{index} |"))
            .collect();
        let body = format!(
            "### All RPM Changes\n| | Name | Previous | New |\n| --- | --- | --- | --- |\n{}",
            rows.join("\n")
        );
        let (title, highlights, package_total) = super::release_highlights(&body);
        assert_eq!(title, "Package changes");
        assert_eq!(package_total, 8);
        assert_eq!(highlights.len(), 8);
        assert!(highlights.contains(&"Updated pkg07 from 1.0-7 to 1.1-7".to_string()));
    }

    #[test]
    fn update_release_summary_ignores_wrong_digest_channel_and_untrusted_tags() {
        let digest = format!("sha256:{}", "b".repeat(64));
        let payload = serde_json::json!([{
            "tag_name": "image-testing-20260925-2481-1-8b81dca7",
            "draft": false,
            "prerelease": true,
            "body": format!("Image: `ghcr.io/kyth-os/kyth@{}`", "sha256:".to_string() + &"a".repeat(64)),
        }]);
        assert!(
            super::update_release_summary_from_api(&payload.to_string(), "testing", &digest)
                .is_none()
        );
        assert!(
            super::update_release_summary_from_api(&payload.to_string(), "other", &digest)
                .is_none()
        );
        assert!(super::image_release_version("testing", "image-testing-../../evil").is_none());
    }

    #[test]
    fn image_release_version_parses_the_cachy_flavor_infix() {
        assert_eq!(
            super::image_release_version("testing", "image-testing-cachy-20261012-2735-1-27a537a0"),
            Some("testing.20261012.2735.1.27a537a0".to_string())
        );
        assert_eq!(
            super::image_release_identity(
                "testing",
                "image-testing-cachy-20261012-2735-1-27a537a0"
            ),
            Some(("testing.20261012.2735.1.27a537a0".to_string(), "cachy"))
        );
        assert_eq!(
            super::image_release_identity("testing", "image-testing-20261012-2735-1-27a537a0"),
            Some(("testing.20261012.2735.1.27a537a0".to_string(), "fedora"))
        );
        assert!(
            super::image_release_version("testing", "image-testing-cachy-../../evil").is_none()
        );
    }

    #[test]
    fn update_release_history_lists_channel_releases_with_notes() {
        let digest_a = format!("sha256:{}", "a".repeat(64));
        let digest_b = format!("sha256:{}", "b".repeat(64));
        let body_a = format!(
            "# Kyth image\n\nBuilt from branch `testing` at commit `aaaaaaaaaaaa`.\n\nImage: `ghcr.io/kyth-os/kyth@{digest_a}`\n\n### Major Package Changes\n| | Name | Previous | New |\n| --- | --- | --- | --- |\n| ~ | `mesa-dri-drivers` | 26.2.3-1 | 26.2.4-1 |\n"
        );
        let body_b = format!(
            "# Kyth image\n\nImage: `ghcr.io/kyth-os/kyth@{digest_b}`\n\nNo previous SBOM was available to compare against.\n\n### Major Packages\n| Name | Version |\n| --- | --- |\n| `gamescope` | 3.16.29-1 |\n"
        );
        let body_c = format!(
            "# Kyth image\n\nImage: `ghcr.io/kyth-os/kyth@{digest_a}`\n\n### Major Packages\n| Name | Version |\n| --- | --- |\n| `gamescope` | 3.16.28-1 |\n"
        );
        let payload = serde_json::json!([
            {"tag_name": "image-testing-20261012-2736-1-aaaaaaaa", "draft": false, "prerelease": true, "published_at": "2026-10-12T22:00:00Z", "body": body_a},
            {"tag_name": "image-testing-cachy-20261013-2735-1-bbbbbbbb", "draft": false, "prerelease": true, "published_at": "2026-10-13T21:00:00Z", "body": body_b},
            {"tag_name": "image-testing-cachy-20261012-2735-1-cccccccc", "draft": false, "prerelease": true, "published_at": "2026-10-12T21:00:00Z", "body": body_c},
            {"tag_name": "image-testing-20261011-2700-1-cccccccc", "draft": true, "prerelease": true, "published_at": "2026-10-11T21:00:00Z", "body": body_a},
            {"tag_name": "iso-testing-20261012-aaaaaaaa-948-1", "draft": false, "prerelease": true, "published_at": "2026-10-12T23:00:00Z", "body": body_a},
            {"tag_name": "image-latest-20261012-2736-1-dddddddd", "draft": false, "prerelease": false, "published_at": "2026-10-12T20:00:00Z", "body": body_a},
        ]);
        let history =
            super::update_release_history_from_api(&payload.to_string(), "testing", "fedora");
        assert_eq!(history.len(), 1);
        assert_eq!(history[0].version, "testing.20261012.2736.1.aaaaaaaa");
        assert_eq!(history[0].flavor, "fedora");
        assert_eq!(history[0].digest, digest_a);
        assert_eq!(history[0].notes_intro, "");
        assert_eq!(history[0].highlights_title, "Package changes");
        assert_eq!(history[0].package_total, 1);
        assert_eq!(
            history[0].highlights,
            ["Updated mesa-dri-drivers from 26.2.3-1 to 26.2.4-1"]
        );
        assert_eq!(history[0].published_at, "2026-10-12T22:00:00Z");
        assert_eq!(
            history[0].release_url,
            "https://github.com/kyth-os/kyth/releases/tag/image-testing-20261012-2736-1-aaaaaaaa"
        );
        let cachy_history =
            super::update_release_history_from_api(&payload.to_string(), "testing", "cachy");
        assert_eq!(cachy_history.len(), 2);
        assert_eq!(cachy_history[0].flavor, "cachy");
        assert_eq!(cachy_history[0].digest, digest_b);
        assert_eq!(cachy_history[0].highlights_title, "Release highlights");
        assert!(cachy_history[0].highlights.is_empty());
        assert!(cachy_history[0].notes_intro.is_empty());
        assert_eq!(cachy_history[1].flavor, "cachy");
        assert!(cachy_history[1].highlights.is_empty());
    }

    #[test]
    fn release_highlights_hide_baseline_inventories() {
        let body = "### Major Packages\n| Name | Version |\n| --- | --- |\n| `mesa-dri-drivers` | 26.2.3-1 |\n";
        let (title, highlights, package_total) = super::release_highlights(body);
        assert_eq!(title, "Release highlights");
        assert!(highlights.is_empty());
        assert_eq!(package_total, 0);
    }

    #[test]
    fn release_highlights_use_complete_changes_instead_of_duplicate_major_rows() {
        let body = "### Major Package Changes\n| | Name | Previous | New |\n| --- | --- | --- | --- |\n| ~ | `mesa` | 1.0 | 2.0 |\n\n### All RPM Changes\n| | Name | Previous | New |\n| --- | --- | --- | --- |\n| ~ | `mesa` | 1.0 | 2.0 |\n| + | `new-tool` |  | 1.0 |\n";
        let (title, highlights, package_total) = super::release_highlights(&body);
        assert_eq!(title, "Package changes");
        assert_eq!(package_total, 2);
        assert_eq!(
            highlights,
            ["Updated mesa from 1.0 to 2.0", "Added new-tool 1.0"]
        );
    }

    #[test]
    fn staged_update_progress_runs_end_to_end_through_the_job_store() {
        let _serial = SLOT_TEST_LOCK.lock().unwrap();
        let slot = take_mutating_slot().expect("take update slot");
        let launch = start_stage_job(
            "stage-test",
            "Test stage",
            vec![
                "/bin/sh".into(),
                "-c".into(),
                "sleep 0.2; printf '%s\\n' 'KYTH_STAGE_PROGRESS pct=15 phase=download detail=Downloading layer 1 of 4'; sleep 5.25; printf '%s\\n' 'KYTH_STAGE_PROGRESS pct=72 phase=install detail=Installing image'; sleep 0.15; printf '%s\\n' 'KYTH_STAGE_PROGRESS pct=90 phase=verify detail=Verifying image'; sleep 0.15; printf '%s\\n' 'KYTH_STAGE_PROGRESS pct=99 phase=finalize detail=Finalizing image'".into(),
            ],
            std::time::Duration::from_secs(10),
            slot,
        )
        .expect("start fake update helper");

        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
        let mut observed = Vec::new();
        let mut heartbeat_seen = false;
        let mut preparation_seen = false;
        loop {
            let snapshot = stage_progress();
            preparation_seen |= snapshot.phase == "prepare"
                && snapshot.detail.contains("checking system readiness");
            assert!(
                !snapshot.detail.contains('?'),
                "progress must be stated directly"
            );
            heartbeat_seen |= snapshot.detail.contains("download is still running");
            if observed.last().copied() != Some(snapshot.pct) {
                observed.push(snapshot.pct);
            }
            let status = update_jobs()
                .status(&launch.job)
                .expect("update job stays tracked");
            if status.0 != "running" {
                assert_eq!(status.0, "complete");
                assert_eq!(status.1, "Test stage complete.");
                assert!(!snapshot.active);
                assert_eq!(snapshot.phase, "finalize");
                break;
            }
            assert!(
                std::time::Instant::now() < deadline,
                "staging did not finish"
            );
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
        assert!(
            observed.contains(&15),
            "download progress was shown: {observed:?}"
        );
        assert!(
            observed.contains(&72),
            "install progress was shown: {observed:?}"
        );
        assert!(
            observed.contains(&90),
            "verification was shown: {observed:?}"
        );
        assert!(
            observed.contains(&99),
            "finalization was shown: {observed:?}"
        );
        assert!(
            preparation_seen,
            "preparation status must appear before download markers"
        );
        assert!(
            heartbeat_seen,
            "quiet downloads must still publish a heartbeat"
        );
        assert!(observed.windows(2).all(|pair| pair[0] <= pair[1]));
    }

    #[test]
    fn stage_line_reader_caps_unterminated_lines_and_continues() {
        let input = format!("{}\nnext\n", "x".repeat(1024));
        let mut reader = std::io::Cursor::new(input.into_bytes());
        let mut line = Vec::new();
        assert_eq!(
            super::read_stage_line(&mut reader, &mut line, 32).unwrap(),
            Some(true)
        );
        assert_eq!(line.len(), 32);
        assert_eq!(
            super::read_stage_line(&mut reader, &mut line, 32).unwrap(),
            Some(false)
        );
        assert_eq!(String::from_utf8_lossy(&line), "next\n");
        assert_eq!(
            super::read_stage_line(&mut reader, &mut line, 32).unwrap(),
            None
        );
    }

    #[test]
    fn bounded_stderr_capture_drains_past_its_memory_limit() {
        let input = vec![b'x'; 128];
        let mut reader = std::io::Cursor::new(input.clone());
        let captured = super::collect_bounded_output(&mut reader, 16).unwrap();
        assert_eq!(reader.position(), input.len() as u64);
        assert_eq!(&captured[..16], &input[..16]);
        assert!(captured.ends_with(b"\n...[truncated]"));
    }

    #[test]
    fn stage_merge_never_moves_the_bar_backwards() {
        let current = super::StageProgressSnapshot {
            pct: 60,
            phase: "download".into(),
            detail: "Downloading layer 20 of 39".into(),
            active: true,
        };
        let stale = super::StageProgressSnapshot {
            pct: 40,
            phase: "download".into(),
            detail: "Downloading layer 12 of 39".into(),
            active: true,
        };
        assert_eq!(super::merge_stage_snapshot(&current, stale).pct, 60);
        let advanced = super::StageProgressSnapshot {
            pct: 61,
            ..current.clone()
        };
        assert_eq!(super::merge_stage_snapshot(&current, advanced).pct, 61);
    }

    #[test]
    fn hub_action_read_only_classification_is_explicit() {
        // Read-only recipes (status/audit/check) skip the hub-action
        // slot; mutating ones — including any variant added later,
        // which is mutating until classified — take it.
        for action in [
            HubAction::UpdateHealth,
            HubAction::ResumeCheck,
            HubAction::DeviceInfo,
            HubAction::StartupApps,
            HubAction::HealthCheck,
            HubAction::GamingStackStatus,
            HubAction::AiDevStatus,
            HubAction::NvidiaStatus,
            HubAction::ListPresets,
            HubAction::ControllerCheck,
            HubAction::SystemAudit,
            HubAction::GamingAudit,
        ] {
            assert!(
                action.is_read_only(),
                "{} must stay read-only",
                action.recipe()
            );
        }
        for action in [
            HubAction::FirmwareUpdate,
            HubAction::ReclaimWindows,
            HubAction::RemoveWaydroid,
            HubAction::EnrollSecureboot,
            HubAction::InstallSteam,
            HubAction::GamingMode,
            HubAction::SetupPrinter,
            HubAction::AiDevSetup,
        ] {
            assert!(
                !action.is_read_only(),
                "{} mutates and must take the slot",
                action.recipe()
            );
        }
    }

    #[test]
    fn mutating_hub_actions_claim_the_slot_before_the_job_exists() {
        // B-H1 pin: the claim must stay ahead of the job start in
        // start_hub_action_job, and read-only actions must stay exempt.
        // The behavioral single-flight test lives with the slot itself
        // in commands::job.
        let source = include_str!("updates.rs");
        let start = source
            .find("fn start_hub_action_job(")
            .expect("hub action launcher");
        let tail = &source[start..];
        let end = tail.find("#[tauri::command]").unwrap_or(tail.len());
        let body = &tail[..end];
        let claim = body
            .find("take_hub_action_slot()")
            .expect("slot claim present");
        let job_start = body
            .find("hub_action_jobs().start(")
            .expect("job start present");
        assert!(
            claim < job_start,
            "slot must be claimed before the job exists"
        );
        assert!(
            body.contains("action.is_read_only()"),
            "read-only actions must bypass the slot"
        );
    }

    #[test]
    fn switch_branch_uses_the_long_transfer_timeout_tier() {
        // M3 pin: `bootc switch` pulls an uncached channel image, so it
        // belongs in the same 3600s tier as staging, not the 300s
        // download-free tier that killed slow-link switches mid-pull.
        let source = include_str!("updates.rs");
        let start = source
            .find("pub(crate) fn bootc_switch_branch(")
            .expect("switch launcher");
        let tail = &source[start..];
        let end = tail.find("#[tauri::command]").unwrap_or(tail.len());
        let body = &tail[..end];
        assert!(body.contains("JobTimeoutClass::LongTransfer"));
    }

    #[test]
    fn stage_cancel_reaps_the_child_clears_progress_and_releases_the_slot() {
        let _serial = SLOT_TEST_LOCK.lock().unwrap();
        let slot = take_mutating_slot().expect("take update slot");
        let launch = start_stage_job(
            "stage-cancel-test",
            "Test stage cancel",
            vec!["/bin/sh".into(), "-c".into(), "sleep 30".into()],
            std::time::Duration::from_secs(30),
            slot,
        )
        .expect("start fake update helper");
        assert!(stage_progress().active);
        assert!(update_jobs().cancel(&launch.job));

        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
        loop {
            let snapshot = stage_progress();
            // Probe-and-release: Ok means the worker dropped the slot on
            // its way out (the temporary guard drops at the semicolon).
            let slot_free = take_mutating_slot().is_ok();
            if !snapshot.active && slot_free {
                break;
            }
            assert!(
                std::time::Instant::now() < deadline,
                "cancelled stage wedged: active={}, slot_free={slot_free}",
                snapshot.active
            );
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
        let status = update_jobs()
            .status(&launch.job)
            .expect("job stays tracked");
        assert_eq!(status.0, "cancelled");
        super::UPDATE_MUTATING.store(false, std::sync::atomic::Ordering::SeqCst);
    }

    #[test]
    fn binary_precheck_fails_missing_and_passes_present() {
        assert_eq!(
            super::require_binary(
                "/nonexistent/kyth-bootc",
                "bootc is not installed on this system."
            ),
            Err("bootc is not installed on this system.".to_string())
        );
        let exe = std::env::current_exe().expect("test exe path");
        assert!(
            super::require_binary(exe.to_str().expect("utf8 exe path"), "unused").is_ok(),
            "a present binary passes the precheck"
        );
    }

    #[test]
    fn hub_shell_launchers_never_touch_the_root_only_bootc_lock() {
        // Regression pin: the Hub shell runs as the user and /run is
        // root-only, so a with_bootc_lock() admission check in any launch
        // command fails with EACCES before the job can start. In-process
        // serialization is take_mutating_slot(); underneath it, the
        // stage/switch helpers hold the bootc flock for their whole run
        // while rollback relies on bootc/ostree's internal sysroot lock.
        let source = include_str!("updates.rs");
        for launcher in [
            "pub(crate) fn bootc_upgrade()",
            "pub(crate) fn bootc_rollback()",
            "pub(crate) fn bootc_switch_branch(",
            "pub(crate) fn apply_staged()",
        ] {
            let start = source.find(launcher).expect("launcher fn");
            let tail = &source[start + launcher.len()..];
            let end = tail
                .find("#[tauri::command]")
                .or_else(|| tail.find("#[cfg(test)]"))
                .unwrap_or(tail.len());
            let body = &tail[..end];
            assert!(
                !body.contains("with_bootc_lock"),
                "{launcher} must not touch the root-only bootc lock from the user shell"
            );
            assert!(
                body.contains("take_mutating_slot()?"),
                "{launcher} must still serialize stacked launches via the mutating slot"
            );
        }
    }

    #[test]
    fn mutating_slot_rejects_a_second_launch_until_released() {
        let _serial = SLOT_TEST_LOCK.lock().unwrap();
        let slot = super::take_mutating_slot().expect("first launch takes the slot");
        assert!(
            super::take_mutating_slot().is_err(),
            "double-click / second tab must fail fast, not spawn a second sudo job"
        );
        drop(slot);
        // The is_ok temporary drops at the end of the assert, releasing
        // the slot; belt-and-braces reset keeps later tests independent.
        assert!(
            super::take_mutating_slot().is_ok(),
            "finished job releases the slot"
        );
        super::UPDATE_MUTATING.store(false, std::sync::atomic::Ordering::SeqCst);
    }
}
