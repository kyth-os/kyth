//! Port of `kyth_shared.system.process` helpers (pure stdlib, no Qt).
//! Mostly re-exports from `probe` in Python; here we port the standalone
//! helpers: is_live_session, strip_ansi, with_idle_inhibit, disk write bytes,
//! format_elapsed/eta/progress.

use std::fs;
use std::io::{self, Read, Write};
use std::os::unix::process::CommandExt;
use std::process::{Command, ExitStatus, Output, Stdio};
use std::sync::atomic::AtomicBool;
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

/// Upper bound on a single captured pipe. Child output is untrusted and
/// unbounded (a compromised helper could stream gigabytes); exceeding the
/// cap fails the run instead of growing the Hub without limit.
pub const MAX_CAPTURE_BYTES: usize = 8 * 1024 * 1024;

fn read_capped(pipe: &mut dyn Read, limit: usize) -> io::Result<Vec<u8>> {
    let mut buf = Vec::new();
    let mut chunk = [0u8; 8192];
    loop {
        let count = pipe.read(&mut chunk)?;
        if count == 0 {
            return Ok(buf);
        }
        if buf.len().saturating_add(count) > limit {
            return Err(io::Error::new(
                io::ErrorKind::OutOfMemory,
                "captured output exceeded its size limit",
            ));
        }
        buf.extend_from_slice(&chunk[..count]);
    }
}

/// Drain a child's stdout/stderr on background threads as soon as it's
/// spawned. A pipe's kernel buffer is a few tens of KB; a command that
/// writes past that (e.g. `ps -eo pid=,args=` on a host with hundreds of
/// processes) blocks in `write()` until something reads. Every caller here
/// only reads after `try_wait()` sees the child has exited, so an
/// unattended child that outgrows the buffer can never exit — it sits
/// blocked until the timeout kills it. Spawning readers up front avoids
/// that deadlock regardless of how much output the command produces.
fn spawn_pipe_readers(
    child: &mut std::process::Child,
) -> (
    JoinHandle<io::Result<Vec<u8>>>,
    JoinHandle<io::Result<Vec<u8>>>,
) {
    let mut stdout = child.stdout.take();
    let mut stderr = child.stderr.take();
    let stdout_reader = std::thread::spawn(move || {
        stdout
            .as_mut()
            .map(|pipe| read_capped(pipe, MAX_CAPTURE_BYTES))
            .unwrap_or(Ok(Vec::new()))
    });
    let stderr_reader = std::thread::spawn(move || {
        stderr
            .as_mut()
            .map(|pipe| read_capped(pipe, MAX_CAPTURE_BYTES))
            .unwrap_or(Ok(Vec::new()))
    });
    (stdout_reader, stderr_reader)
}

fn collect_output(
    status: ExitStatus,
    stdout_reader: JoinHandle<io::Result<Vec<u8>>>,
    stderr_reader: JoinHandle<io::Result<Vec<u8>>>,
) -> io::Result<Output> {
    let stdout = stdout_reader
        .join()
        .map_err(|_| io::Error::new(io::ErrorKind::Other, "output reader panicked"))??;
    let stderr = stderr_reader
        .join()
        .map_err(|_| io::Error::new(io::ErrorKind::Other, "output reader panicked"))??;
    Ok(Output {
        status,
        stdout,
        stderr,
    })
}

/// Kill a child and everything it forked. Hub-spawned commands (`flatpak`
/// pulls, `just` recipes, `sudo openconnect`) fork grandchildren that
/// survive a direct `child.kill()`; without a group kill, timed-out or
/// cancelled work keeps running detached from the job that reported it.
/// Children here are spawned as group leaders (see `process_group(0)` at
/// each spawn below), so the child's pid is the generation's pgid.
pub fn kill_process_group(child: &mut std::process::Child) {
    let _ = child.kill();
    let _ = unsafe { libc::killpg(child.id() as libc::pid_t, libc::SIGKILL) };
}

fn kill_tree(child: &mut std::process::Child) {
    kill_process_group(child);
    let _ = child.wait();
}

/// Kill stale focus-session inhibitors from a previous Hub process.
///
/// `focus_start` spawns `systemd-inhibit … sleep N`; when the Hub crashes
/// or restarts, that child reparents and keeps holding the idle:sleep
/// block with nothing tracking it — a laptop silently stops suspending
/// for up to 4h. Only processes whose full command line carries BOTH the
/// systemd-inhibit binary and our exact `--why` marker are touched, and
/// `keep_pids` (the current process's live sessions) are spared, so a new
/// session never murders a sibling's inhibit. Returns kills sent.
pub fn reap_stale_focus_inhibits(keep_pids: &[u32]) -> usize {
    reap_stale_focus_inhibits_at(std::path::Path::new("/proc"), keep_pids)
}

fn reap_stale_focus_inhibits_at(proc: &std::path::Path, keep_pids: &[u32]) -> usize {
    let Ok(entries) = std::fs::read_dir(proc) else {
        return 0;
    };
    let mut killed = 0;
    for entry in entries.flatten() {
        let pid: u32 = match entry.file_name().to_string_lossy().parse() {
            Ok(pid) => pid,
            Err(_) => continue,
        };
        if pid == std::process::id() || keep_pids.contains(&pid) {
            continue;
        }
        let cmdline = std::fs::read(entry.path().join("cmdline")).unwrap_or_default();
        let parts: Vec<&str> = cmdline
            .split(|byte| *byte == b'\0')
            .filter_map(|part| std::str::from_utf8(part).ok())
            .filter(|part| !part.is_empty())
            .collect();
        let Some(first) = parts.first() else {
            continue;
        };
        let is_inhibit = first.ends_with("/systemd-inhibit") || *first == "systemd-inhibit";
        if !is_inhibit {
            continue;
        }
        if !parts
            .iter()
            .any(|part| *part == "--why=KythOS Focus Session")
        {
            continue;
        }
        // TERM first so systemd-inhibit releases the lock cleanly; the
        // orphaned `sleep` it leaves behind blocks nothing on its own.
        unsafe {
            libc::kill(pid as libc::pid_t, libc::SIGTERM);
        }
        killed += 1;
    }
    killed
}

/// Launch a GUI or otherwise long-lived child without blocking the caller
/// and without leaking a zombie: a background thread reaps the exit status
/// whenever the child exits. For bounded work with captured output, use the
/// `run_bounded*` runners instead.
pub fn spawn_detached(command: &mut Command) -> io::Result<()> {
    let mut child = command.spawn()?;
    std::thread::spawn(move || {
        let _ = child.wait();
    });
    Ok(())
}

/// Run an already-validated argv with captured output and a hard wall-clock
/// limit. It never invokes a shell and kills a child that outlives its bound.
pub fn run_bounded(argv: &[String], timeout: Duration) -> io::Result<Output> {
    let (program, args) = argv
        .split_first()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "command must not be empty"))?;
    let mut command = Command::new(program);
    command.args(args);
    run_bounded_command(command, timeout)
}

/// Run a fixed argv while supplying bounded sensitive input through stdin.
/// The input is never part of the process arguments or captured status text.
pub fn run_bounded_with_input(
    argv: &[String],
    input: &[u8],
    timeout: Duration,
) -> io::Result<Output> {
    let (program, args) = argv
        .split_first()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "command must not be empty"))?;
    let mut command = Command::new(program);
    command.args(args).stdin(Stdio::piped());
    // Own process group so a timeout kill reaches forked grandchildren too.
    command.process_group(0);
    let mut child = command
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    let (stdout_reader, stderr_reader) = spawn_pipe_readers(&mut child);
    // Write stdin from a detached thread, never the wait loop: a child
    // that exits without reading (or stops reading mid-stream) leaves no
    // reader on the pipe, so a synchronous write_all here would block
    // past the timeout — or fail the whole run with EPIPE — while the
    // reaped status below already answers the call.
    if let Some(mut stdin) = child.stdin.take() {
        let owned = input.to_vec();
        std::thread::spawn(move || {
            let _ = stdin.write_all(&owned);
        });
    }
    let started = Instant::now();
    loop {
        match child.try_wait()? {
            Some(status) => return collect_output(status, stdout_reader, stderr_reader),
            None if started.elapsed() <= timeout => std::thread::sleep(Duration::from_millis(25)),
            None => {
                kill_tree(&mut child);
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "command exceeded its time limit",
                ));
            }
        }
    }
}

pub fn run_bounded_command(command: Command, timeout: Duration) -> io::Result<Output> {
    run_bounded_command_cancel(command, timeout, &AtomicBool::new(false))
}

/// Same as [`run_bounded_command`], but a worker thread can abort early by
/// setting `cancel`: the child is killed within one poll tick and the call
/// returns an `Interrupted` error instead of blocking until `timeout`.
/// Backs Hub job cancellation in `system::jobs::JobStore`.
pub fn run_bounded_command_cancel(
    mut command: Command,
    timeout: Duration,
    cancel: &AtomicBool,
) -> io::Result<Output> {
    use std::sync::atomic::Ordering::Relaxed;
    // Own process group so timeout/cancel kills reach forked grandchildren.
    command.process_group(0);
    let mut child = command
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    let (stdout_reader, stderr_reader) = spawn_pipe_readers(&mut child);
    let started = Instant::now();
    loop {
        match child.try_wait()? {
            Some(status) => return collect_output(status, stdout_reader, stderr_reader),
            None if cancel.load(Relaxed) => {
                kill_tree(&mut child);
                return Err(io::Error::new(
                    io::ErrorKind::Interrupted,
                    "command was cancelled",
                ));
            }
            None if started.elapsed() <= timeout => std::thread::sleep(Duration::from_millis(25)),
            None => {
                kill_tree(&mut child);
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "command exceeded its time limit",
                ));
            }
        }
    }
}

pub fn is_live_session() -> bool {
    fs::read_to_string("/proc/cmdline")
        .map(|s| s.contains("kyth.live"))
        .unwrap_or(false)
}

pub fn strip_ansi(text: &str) -> String {
    // Mirrors re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
    let mut out = String::with_capacity(text.len());
    let mut chars = text.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\x1b' {
            if chars.peek() == Some(&'[') {
                chars.next(); // '['
                while let Some(&next) = chars.peek() {
                    if next.is_ascii_alphabetic() {
                        chars.next();
                        break;
                    } else if next.is_ascii_digit() || next == ';' {
                        chars.next();
                    } else {
                        break;
                    }
                }
                continue;
            }
        }
        out.push(c);
    }
    out
}

/// Remove common secret-bearing `key=value`/`key: value` fields from text
/// before it is placed in a job status, diagnostic, or audit record.
///
/// This is intentionally a defense-in-depth filter. Secret-bearing commands
/// must still use stdin and avoid putting credentials in argv; this helper
/// protects the UI/log boundary if a child unexpectedly echoes a credential.
pub fn redact_sensitive_text(text: &str) -> String {
    text.lines()
        .map(redact_sensitive_line)
        .collect::<Vec<_>>()
        .join("\n")
}

fn redact_sensitive_line(line: &str) -> String {
    let mut redacted = line.to_string();
    loop {
        let next = redact_sensitive_line_once(&redacted);
        if next == redacted {
            return redacted;
        }
        redacted = next;
    }
}

fn redact_sensitive_line_once(line: &str) -> String {
    const MARKERS: &[&str] = &[
        "password",
        "passwd",
        "passphrase",
        "secret",
        "token",
        "cookie",
        "authcookie",
        "samlresponse",
        "bitlocker_key",
        "authorization",
        "key",
    ];
    let lower = line.to_ascii_lowercase();
    for marker in MARKERS {
        let mut search_from = 0;
        while let Some(relative) = lower[search_from..].find(marker) {
            let start = search_from + relative;
            let end = start + marker.len();
            let boundary_before = start == 0
                || !lower.as_bytes()[start - 1].is_ascii_alphanumeric()
                    && lower.as_bytes()[start - 1] != b'_';
            let boundary_after = end == lower.len()
                || !lower.as_bytes()[end].is_ascii_alphanumeric() && lower.as_bytes()[end] != b'_';
            if !boundary_before || !boundary_after {
                search_from = end;
                continue;
            }
            let mut delimiter = end;
            if line
                .as_bytes()
                .get(delimiter)
                .is_some_and(|byte| matches!(byte, b'"' | b'\''))
            {
                delimiter += 1;
            }
            while delimiter < line.len() && line.as_bytes()[delimiter].is_ascii_whitespace() {
                delimiter += 1;
            }
            if delimiter >= line.len() || !matches!(line.as_bytes()[delimiter], b'=' | b':') {
                search_from = end;
                continue;
            }
            let mut value_start = delimiter + 1;
            while value_start < line.len() && line.as_bytes()[value_start].is_ascii_whitespace() {
                value_start += 1;
            }
            let quote = line
                .as_bytes()
                .get(value_start)
                .copied()
                .filter(|byte| matches!(byte, b'"' | b'\''));
            if quote.is_some() {
                value_start += 1;
            }
            let mut value_end = value_start;
            if let Some(quote) = quote {
                while value_end < line.len() && line.as_bytes()[value_end] != quote {
                    value_end += 1;
                }
            } else {
                while value_end < line.len()
                    && !line.as_bytes()[value_end].is_ascii_whitespace()
                    && !matches!(
                        line.as_bytes()[value_end],
                        b',' | b';' | b'&' | b'"' | b'\'' | b']' | b'}'
                    )
                {
                    value_end += 1;
                }
            }
            if value_start == value_end {
                search_from = end;
                continue;
            }
            if &line[value_start..value_end] == "<redacted>" {
                search_from = value_end;
                continue;
            }
            let mut redacted = String::with_capacity(line.len());
            redacted.push_str(&line[..value_start]);
            redacted.push_str("<redacted>");
            redacted.push_str(&line[value_end..]);
            return redacted;
        }
    }
    line.to_string()
}

pub fn with_idle_inhibit(cmd: &[String], reason: &str) -> Vec<String> {
    let has = which("systemd-inhibit");
    if !has {
        return cmd.to_vec();
    }
    let mut v = vec![
        "systemd-inhibit".to_string(),
        "--what=idle:sleep".to_string(),
        format!("--why={}", reason),
        "--mode=block".to_string(),
    ];
    v.extend_from_slice(cmd);
    v
}

fn which(cmd: &str) -> bool {
    if let Ok(path) = std::env::var("PATH") {
        for dir in path.split(':') {
            if std::path::Path::new(dir).join(cmd).exists() {
                return true;
            }
        }
    }
    false
}

pub fn get_disk_write_bytes() -> u64 {
    if let Ok(text) = fs::read_to_string("/proc/diskstats") {
        let mut total: u64 = 0;
        for line in text.lines() {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() >= 10 {
                if let Ok(v) = parts[9].parse::<u64>() {
                    total += v;
                }
            }
        }
        return total * 512;
    }
    0
}

pub fn format_elapsed(seconds: i64) -> String {
    let s = seconds.max(0);
    let mins = s / 60;
    let secs = s % 60;
    if mins > 0 {
        format!("{}m {:02}s", mins, secs)
    } else {
        format!("{}s", secs)
    }
}

pub fn format_eta(seconds: i64) -> String {
    if seconds > 60 {
        format!("~{} remaining", format_elapsed(seconds))
    } else if seconds > 0 {
        format!("~{}s remaining", seconds)
    } else {
        String::new()
    }
}

pub fn format_dl_progress_line(
    downloaded: u64,
    total: u64,
    speed_bps: u64,
    eta_sec: i64,
) -> String {
    let dl_d = human_bytes(downloaded);
    let dl_t = human_bytes(total);
    let sp = human_bytes(speed_bps);
    let mut parts = vec![format!("{} / {}", dl_d, dl_t), format!("{}/s", sp)];
    let eta = format_eta(eta_sec);
    if !eta.is_empty() {
        parts.push(eta);
    }
    parts.join("  ·  ")
}

fn human_bytes(n: u64) -> String {
    const UNITS: &[&str] = &["B", "KB", "MB", "GB", "TB"];
    let mut v = n as f64;
    let mut idx = 0;
    while v >= 1024.0 && idx < UNITS.len() - 1 {
        v /= 1024.0;
        idx += 1;
    }
    if idx == 0 {
        format!("{} {}", n, UNITS[idx])
    } else {
        format!("{:.1} {}", v, UNITS[idx])
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;
    #[test]
    fn stale_focus_reaper_kills_only_marked_inhibits() {
        // Skip-paths use fake PIDs (never signalled — only entries
        // matching BOTH the binary and the marker reach kill()). The one
        // matching entry is a real `sleep` child this test owns, disguised
        // via fake /proc, so the kill lands on nothing foreign.
        let dir = tempfile::tempdir().unwrap();
        let fake = |pid: &str, cmd: &[u8]| {
            let entry = dir.path().join(pid);
            std::fs::create_dir_all(&entry).unwrap();
            std::fs::write(entry.join("cmdline"), cmd).unwrap();
        };
        fake(
            "1001",
            b"systemd-inhibit\0--what=idle:sleep\0--why=Something Else\0sleep\0",
        );
        fake("1002", b"sleep\0");
        fake("self", b"systemd-inhibit\0--why=KythOS Focus Session\0");
        let mut owned = std::process::Command::new("sleep")
            .arg("300")
            .spawn()
            .expect("sleep must exist for the reaper test");
        let pid = owned.id();
        fake(
            &pid.to_string(),
            b"systemd-inhibit\0--what=idle:sleep\0--why=KythOS Focus Session\0sleep\0",
        );
        // A kept PID is spared even when marked.
        assert_eq!(reap_stale_focus_inhibits_at(dir.path(), &[pid]), 0);
        assert!(owned.try_wait().unwrap().is_none());
        // Unkept and marked: TERM sent, child actually dies.
        assert_eq!(reap_stale_focus_inhibits_at(dir.path(), &[]), 1);
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
        loop {
            if owned.try_wait().unwrap().is_some() {
                break;
            }
            assert!(
                std::time::Instant::now() < deadline,
                "TERMed child must exit"
            );
            std::thread::sleep(std::time::Duration::from_millis(25));
        }
    }

    #[test]
    fn strip() {
        assert_eq!(strip_ansi("\x1b[31mred\x1b[0m"), "red");
    }

    #[test]
    fn sensitive_output_is_redacted_without_destroying_context() {
        let detail = "operation failed password=super-secret; retryable=true\nstatus: token=token-value\n{\"password\":\"json-secret\"}";
        let redacted = redact_sensitive_text(detail);
        assert!(!redacted.contains("super-secret"));
        assert!(!redacted.contains("token-value"));
        assert!(!redacted.contains("json-secret"));
        assert!(redacted.contains("operation failed password=<redacted>; retryable=true"));
        assert!(redacted.contains("status: token=<redacted>"));
    }

    #[test]
    fn sensitive_output_redacts_multiple_fields_on_one_line() {
        let redacted = redact_sensitive_text("password=first token=second secret=third");
        assert_eq!(
            redacted,
            "password=<redacted> token=<redacted> secret=<redacted>"
        );
    }
    #[test]
    fn elapsed() {
        assert_eq!(format_elapsed(70), "1m 10s");
        assert_eq!(format_elapsed(5), "5s");
    }
    #[test]
    fn eta() {
        assert_eq!(format_eta(90), "~1m 30s remaining");
    }

    #[test]
    fn cancel_kills_forked_grandchildren_not_just_the_child() {
        // `bash -c 'sleep 60'` leaves `sleep` as a grandchild of the test.
        // A direct child.kill() would orphan it; the group kill must reap it.
        let marker = "kyth-killtree-probe-sleep";
        let cancel = std::sync::Arc::new(AtomicBool::new(false));
        let mut command = Command::new("bash");
        command.args(["-c".to_string(), format!("exec -a {marker} sleep 60")]);
        let cancel_worker = cancel.clone();
        let handle = std::thread::spawn(move || {
            run_bounded_command_cancel(command, Duration::from_secs(60), &cancel_worker)
        });
        // Wait for the grandchild to exist before cancelling.
        let mut seen = false;
        for _ in 0..100 {
            let probe = Command::new("pgrep").arg("-f").arg(marker).output();
            if probe.map(|out| out.status.success()).unwrap_or(false) {
                seen = true;
                break;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        assert!(seen, "grandchild sleep should have started");
        cancel.store(true, std::sync::atomic::Ordering::Relaxed);
        let result = handle.join().expect("runner thread joins");
        assert_eq!(
            result.map_err(|error| error.kind()),
            Err(std::io::ErrorKind::Interrupted)
        );
        // The grandchild must be gone, not orphaned.
        for _ in 0..100 {
            let probe = Command::new("pgrep").arg("-f").arg(marker).output();
            if !probe.map(|out| out.status.success()).unwrap_or(true) {
                return;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        panic!("grandchild {marker} survived cancellation");
    }

    #[test]
    fn bounded_runner_captures_a_static_argv_without_a_shell() {
        let output = run_bounded(
            &["sh".into(), "-c".into(), "printf ok".into()],
            Duration::from_secs(2),
        )
        .unwrap();
        assert!(output.status.success());
        assert_eq!(output.stdout, b"ok");
    }

    /// A child writing more than a pipe's kernel buffer (tens of KB) blocks
    /// in `write()` until something reads. If nothing drains stdout until
    /// after `try_wait()` reports the child has exited, that child can never
    /// exit — real-world case: `ps -eo pid=,args=` on a host with hundreds
    /// of processes, called from `bootc_query::active_operation()` on every
    /// probe run. This must finish well under the command's own timeout,
    /// not by surviving on a raised limit.
    #[test]
    fn bounded_runner_drains_output_larger_than_a_pipe_buffer_without_deadlocking() {
        let started = Instant::now();
        let output = run_bounded(
            &["sh".into(), "-c".into(), "yes x | head -c 1000000".into()],
            Duration::from_secs(5),
        )
        .unwrap();
        assert!(output.status.success());
        assert_eq!(output.stdout.len(), 1_000_000);
        assert!(
            started.elapsed() < Duration::from_secs(2),
            "took {:?}, should complete almost immediately once pipes are drained",
            started.elapsed()
        );
    }

    #[test]
    fn bounded_runner_terminates_a_stalled_child() {
        let error = run_bounded(
            &["sh".into(), "-c".into(), "sleep 1".into()],
            Duration::from_millis(50),
        )
        .unwrap_err();
        assert_eq!(error.kind(), std::io::ErrorKind::TimedOut);
    }

    #[test]
    fn cancellable_runner_kills_a_stalled_child_within_one_tick() {
        use std::sync::atomic::Ordering::Relaxed;
        use std::sync::Arc;
        let cancel = Arc::new(AtomicBool::new(false));
        let flag = cancel.clone();
        let started = Instant::now();
        let handle = std::thread::spawn(move || {
            let mut command = Command::new("sh");
            command.args(["-c", "sleep 30"]);
            run_bounded_command_cancel(command, Duration::from_secs(30), &flag).unwrap_err()
        });
        std::thread::sleep(Duration::from_millis(100));
        cancel.store(true, Relaxed);
        let error = handle.join().unwrap();
        assert_eq!(error.kind(), std::io::ErrorKind::Interrupted);
        assert!(
            started.elapsed() < Duration::from_secs(5),
            "cancel must beat the 30s timeout"
        );
    }

    #[test]
    fn bounded_runner_supplies_input_without_putting_it_in_argv() {
        let output = run_bounded_with_input(
            &["sh".into(), "-c".into(), "cat".into()],
            b"secret",
            Duration::from_secs(2),
        )
        .unwrap();
        assert_eq!(output.stdout, b"secret");
    }

    #[test]
    fn input_writer_never_blocks_a_child_that_exits_without_reading() {
        // More than a pipe's kernel buffer, handed to a child that exits
        // without reading a byte: the stdin write must live on its own
        // thread (absorbing EPIPE there) so the wait loop below still
        // reaps the real status instead of failing the run.
        let oversized = vec![b'x'; 1024 * 1024];
        let started = Instant::now();
        let output =
            run_bounded_with_input(&["true".into()], &oversized, Duration::from_secs(5)).unwrap();
        assert!(output.status.success());
        assert!(
            started.elapsed() < Duration::from_secs(5),
            "took {:?}, the writer thread must not stall the reap",
            started.elapsed()
        );
    }

    #[test]
    fn capped_reader_fails_past_eight_mib() {
        assert_eq!(MAX_CAPTURE_BYTES, 8 * 1024 * 1024);
        let oversized = vec![b'x'; MAX_CAPTURE_BYTES + 1];
        let mut cursor: &[u8] = &oversized;
        let error = read_capped(&mut cursor, MAX_CAPTURE_BYTES).unwrap_err();
        assert_eq!(error.kind(), std::io::ErrorKind::OutOfMemory);
        let exact = vec![b'y'; 16];
        let mut cursor: &[u8] = &exact;
        assert_eq!(read_capped(&mut cursor, MAX_CAPTURE_BYTES).unwrap(), exact);
    }
}
