//! Port of `kyth_shared.system.process` helpers (pure stdlib, no Qt).
//! Mostly re-exports from `probe` in Python; here we port the standalone
//! helpers: is_live_session, strip_ansi, with_idle_inhibit, disk write bytes,
//! format_elapsed/eta/progress.

use std::fs;
use std::io;
use std::process::{Command, Output, Stdio};
use std::time::{Duration, Instant};

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

pub fn run_bounded_command(mut command: Command, timeout: Duration) -> io::Result<Output> {
    let mut child = command.stdout(Stdio::piped()).stderr(Stdio::piped()).spawn()?;
    let started = Instant::now();
    loop {
        match child.try_wait()? {
            Some(_) => return child.wait_with_output(),
            None if started.elapsed() <= timeout => std::thread::sleep(Duration::from_millis(25)),
            None => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(io::Error::new(io::ErrorKind::TimedOut, "command exceeded its time limit"));
            }
        }
    }
}

pub fn is_live_session() -> bool {
    fs::read_to_string("/proc/cmdline").map(|s| s.contains("kyth.live")).unwrap_or(false)
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
                    if next.is_ascii_alphabetic() { chars.next(); break; }
                    else if next.is_ascii_digit() || next == ';' { chars.next(); }
                    else { break; }
                }
                continue;
            }
        }
        out.push(c);
    }
    out
}

pub fn with_idle_inhibit(cmd: &[String], reason: &str) -> Vec<String> {
    let has = which("systemd-inhibit");
    if !has { return cmd.to_vec(); }
    let mut v = vec!["systemd-inhibit".to_string(), "--what=idle:sleep".to_string(), format!("--why={}", reason), "--mode=block".to_string()];
    v.extend_from_slice(cmd);
    v
}

fn which(cmd: &str) -> bool {
    if let Ok(path) = std::env::var("PATH") {
        for dir in path.split(':') { if std::path::Path::new(dir).join(cmd).exists() { return true; } }
    }
    false
}

pub fn get_disk_write_bytes() -> u64 {
    if let Ok(text) = fs::read_to_string("/proc/diskstats") {
        let mut total: u64 = 0;
        for line in text.lines() {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() >= 10 {
                if let Ok(v) = parts[9].parse::<u64>() { total += v; }
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
    if mins > 0 { format!("{}m {:02}s", mins, secs) } else { format!("{}s", secs) }
}

pub fn format_eta(seconds: i64) -> String {
    if seconds > 60 { format!("~{} remaining", format_elapsed(seconds)) }
    else if seconds > 0 { format!("~{}s remaining", seconds) }
    else { String::new() }
}

pub fn format_dl_progress_line(downloaded: u64, total: u64, speed_bps: u64, eta_sec: i64) -> String {
    let dl_d = human_bytes(downloaded);
    let dl_t = human_bytes(total);
    let sp = human_bytes(speed_bps);
    let mut parts = vec![format!("{} / {}", dl_d, dl_t), format!("{}/s", sp)];
    let eta = format_eta(eta_sec);
    if !eta.is_empty() { parts.push(eta); }
    parts.join("  ·  ")
}

fn human_bytes(n: u64) -> String {
    const UNITS: &[&str] = &["B","KB","MB","GB","TB"];
    let mut v = n as f64;
    let mut idx = 0;
    while v >= 1024.0 && idx < UNITS.len()-1 { v/=1024.0; idx+=1; }
    if idx==0 { format!("{} {}", n, UNITS[idx]) } else { format!("{:.1} {}", v, UNITS[idx]) }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;
    #[test]
    fn strip() { assert_eq!(strip_ansi("\x1b[31mred\x1b[0m"), "red"); }
    #[test]
    fn elapsed() { assert_eq!(format_elapsed(70), "1m 10s"); assert_eq!(format_elapsed(5), "5s"); }
    #[test]
    fn eta() { assert_eq!(format_eta(90), "~1m 30s remaining"); }

    #[test]
    fn bounded_runner_captures_a_static_argv_without_a_shell() {
        let output = run_bounded(&["sh".into(), "-c".into(), "printf ok".into()], Duration::from_secs(2)).unwrap();
        assert!(output.status.success());
        assert_eq!(output.stdout, b"ok");
    }

    #[test]
    fn bounded_runner_terminates_a_stalled_child() {
        let error = run_bounded(&["sh".into(), "-c".into(), "sleep 1".into()], Duration::from_millis(50)).unwrap_err();
        assert_eq!(error.kind(), std::io::ErrorKind::TimedOut);
    }
}
