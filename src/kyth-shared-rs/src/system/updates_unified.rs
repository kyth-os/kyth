//! Port of `kyth_shared.system.updates_unified` — bootc + flatpak + firmware.

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

pub fn pending_updates_summary() -> std::collections::HashMap<String, String> {
    let mut out = std::collections::HashMap::new();
    // firmware via existing check (reuse: call fwupdmgr? simplified to "0" like Python fallback)
    out.insert("firmware".to_string(), "0".to_string());
    // flatpak
    let flatpak = run_with_timeout("flatpak", &["remote-ls", "--updates"], Duration::from_secs(15))
        .and_then(|(code, stdout)| if code == 0 { Some(stdout.lines().filter(|l| !l.trim().is_empty()).count().to_string()) } else { Some("0".to_string()) })
        .unwrap_or_else(|| "0".to_string());
    out.insert("flatpak".to_string(), flatpak);
    // bootc
    let bootc = run_with_timeout("bootc", &["status", "--json"], Duration::from_secs(10))
        .map(|(_, stdout)| if stdout.to_lowercase().contains("staged") { "staged" } else { "current" }.to_string())
        .unwrap_or_else(|| "unknown".to_string());
    out.insert("bootc".to_string(), bootc);
    out
}

pub fn rollback_command() -> Vec<String> {
    vec!["bootc".to_string(), "rollback".to_string()]
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn summary_has_keys() {
        let m = pending_updates_summary();
        assert!(m.contains_key("bootc"));
        assert!(m.contains_key("flatpak"));
        assert!(m.contains_key("firmware"));
    }
    #[test]
    fn rollback() {
        assert_eq!(rollback_command(), vec!["bootc", "rollback"]);
    }
}
