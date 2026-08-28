//! Port of `kyth_shared.system.btrfs_status` — maint.jsonl + scrub status (N16).

use std::path::Path;
use std::process::Command;
use std::time::Duration;

const MAINT: &str = "/var/log/kyth/maint.jsonl";

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

pub fn btrfs_health_summary() -> (String, String) {
    if let Some((0, stdout)) = run_with_timeout("btrfs", &["scrub", "status", "/"], Duration::from_secs(5)) {
        if stdout.to_lowercase().contains("running") {
            return ("warn".to_string(), "btrfs scrub running".to_string());
        }
    }
    let path = Path::new(MAINT);
    if path.exists() {
        if let Ok(text) = std::fs::read_to_string(path) {
            if let Some(line) = text.trim().lines().last() {
                if let Ok(v) = serde_json::from_str::<serde_json::Value>(line) {
                    let status = v.get("status").and_then(|s| s.as_str()).unwrap_or("ok").to_string();
                    let msg = v.get("msg").and_then(|s| s.as_str()).unwrap_or("btrfs maint idle").to_string();
                    return (status, msg);
                }
            }
        }
    }
    ("ok".to_string(), "btrfs maint idle (PSI/AC gated)".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn returns_tuple() {
        let (s, m) = btrfs_health_summary();
        assert!(!s.is_empty());
        assert!(!m.is_empty());
    }
}
