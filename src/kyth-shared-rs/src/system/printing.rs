//! Port of `kyth_shared.system.printing` — Mint IPP parity (N34).

use std::process::Command;
use std::time::Duration;

fn run_with_timeout(cmd: &str, args: &[&str], timeout: Duration) -> Option<(i32, String)> {
    use std::process::Stdio;
    let mut child = Command::new(cmd).args(args).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().ok()?;
    let start = std::time::Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(s)) => {
                let out = child.wait_with_output().ok()?;
                return Some((s.code().unwrap_or(-1), String::from_utf8_lossy(&out.stdout).to_string()));
            }
            Ok(None) => {
                if start.elapsed() > timeout {
                    let _ = child.kill();
                    let _ = child.wait();
                    return None;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            Err(_) => return None,
        }
    }
}

pub fn ipp_discover() -> Vec<String> {
    if let Some((0, stdout)) = run_with_timeout("ippfind", &[], Duration::from_secs(10)) {
        let v: Vec<String> = stdout.lines().map(|l| l.trim().to_string()).filter(|l| !l.is_empty()).take(20).collect();
        if !v.is_empty() {
            return v;
        }
    }
    if let Some((0, stdout)) = run_with_timeout("lpstat", &["-e"], Duration::from_secs(5)) {
        let v: Vec<String> = stdout.lines().map(|l| l.trim().to_string()).filter(|l| !l.is_empty()).take(20).collect();
        if !v.is_empty() {
            return v;
        }
    }
    Vec::new()
}

pub fn printer_setup_command() -> Vec<String> {
    vec!["system-config-printer".to_string(), "--setup".to_string()]
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn setup_command() {
        assert_eq!(printer_setup_command(), vec!["system-config-printer", "--setup"]);
    }
    #[test]
    fn discover_returns_vec() {
        let v = ipp_discover();
        assert!(v.len() <= 20);
    }
}
