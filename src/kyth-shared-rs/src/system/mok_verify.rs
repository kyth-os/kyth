//! Port of `kyth_shared.system.mok_verify` — Nobara parity (N40).
//!
//! Faithful: `mokutil --sb-state` → enabled/disabled/unknown + `mokutil
//! --list-enrolled` → KythOS Secure Boot enrolled check. 5s timeout each,
//! `FileNotFound` → unknown/mokutil not installed.

use std::process::Command;
use std::time::Duration;

use serde::Serialize;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct MokStatus {
    pub sb_state: String,
    pub enrolled: String,
}

fn run_with_timeout(cmd: &str, args: &[&str], timeout: Duration) -> Option<(i32, String, String)> {
    use std::process::Stdio;
    let mut child = Command::new(cmd)
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .ok()?;
    // Simple timeout via wait_timeout pattern: poll with elapsed
    let start = std::time::Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                let output = child.wait_with_output().ok()?;
                let code = status.code().unwrap_or(-1);
                let stdout = String::from_utf8_lossy(&output.stdout).to_string();
                let stderr = String::from_utf8_lossy(&output.stderr).to_string();
                let _ = stderr;
                return Some((code, stdout, String::new()));
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

pub fn mok_status() -> MokStatus {
    let sb_result = run_with_timeout("mokutil", &["--sb-state"], Duration::from_secs(5));
    let (sb_state, enrolled) = match sb_result {
        None => {
            // Check if mokutil missing vs timeout — try to detect FileNotFound
            // `run_with_timeout` returns None on spawn failure or timeout. Distinguish
            // by probing existence via `which`-like check: attempt spawn and see error kind.
            // Simpler: try Command::new("mokutil").output() error mapping done implicitly
            // as unknown / mokutil not installed mirrors Python's FileNotFound branch.
            // We'll probe via std::process::Command existence check.
            let exists = Command::new("mokutil").arg("--help").output().is_ok();
            if !exists {
                return MokStatus { sb_state: "unknown".to_string(), enrolled: "mokutil not installed".to_string() };
            }
            ("unknown".to_string(), "unknown".to_string())
        }
        Some((code, stdout, _)) => {
            let lower = stdout.to_lowercase();
            let sb = if code == 0 && lower.contains("secureboot enabled") {
                "enabled"
            } else if lower.contains("disabled") {
                "disabled"
            } else {
                "unknown"
            };
            // second call
            let r2 = run_with_timeout("mokutil", &["--list-enrolled"], Duration::from_secs(5));
            let enrolled = match r2 {
                Some((c2, out2, _)) if c2 == 0 && out2.contains("KythOS Secure Boot") => "enrolled",
                Some((c2, _, _)) if c2 == 0 => "not enrolled",
                _ => "not enrolled",
            };
            (sb.to_string(), enrolled.to_string())
        }
    };
    MokStatus { sb_state, enrolled }
}

// Test helper: parse logic without spawning
fn parse_sb(stdout: &str, code: i32) -> &'static str {
    let lower = stdout.to_lowercase();
    if code == 0 && lower.contains("secureboot enabled") {
        "enabled"
    } else if lower.contains("disabled") {
        "disabled"
    } else {
        "unknown"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_enabled() {
        assert_eq!(parse_sb("SecureBoot enabled", 0), "enabled");
        assert_eq!(parse_sb("SecureBoot enabled\n", 0), "enabled");
    }

    #[test]
    fn parse_disabled() {
        assert_eq!(parse_sb("SecureBoot disabled", 0), "disabled");
        assert_eq!(parse_sb("disabled", 1), "disabled");
    }

    #[test]
    fn parse_unknown() {
        assert_eq!(parse_sb("", 0), "unknown");
        assert_eq!(parse_sb("some error", 1), "unknown");
    }
}
