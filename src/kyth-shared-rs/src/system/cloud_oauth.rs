//! Port of `kyth_shared.system.cloud_oauth` — Aurora rclone parity (N36).

use std::process::Command;
use std::time::Duration;

pub fn rclone_oauth_command(remote: &str) -> Vec<String> {
    vec![
        "rclone".to_string(),
        "config".to_string(),
        "create".to_string(),
        remote.to_string(),
        "onedrive".to_string(),
        "--all".to_string(),
    ]
}

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

pub fn cloud_oauth_status() -> (bool, String) {
    match run_with_timeout("rclone", &["listremotes"], Duration::from_secs(5)) {
        Some((0, stdout)) => {
            let rems: Vec<String> = stdout.lines().map(|l| l.trim().to_string()).filter(|l| !l.is_empty()).collect();
            (true, format!("rclone remotes: {}", if rems.is_empty() { "none".to_string() } else { rems.join(", ") }))
        }
        Some((_, _)) => (false, "rclone not configured — use Hub Cloud Storage OAuth".to_string()),
        None => {
            // FileNotFound vs timeout: probe existence
            let exists = Command::new("rclone").arg("version").output().is_ok();
            if !exists {
                (false, "rclone not installed".to_string())
            } else {
                (false, "rclone timeout".to_string())
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn oauth_command() {
        assert_eq!(rclone_oauth_command("onedrive"), vec!["rclone", "config", "create", "onedrive", "onedrive", "--all"]);
    }
    #[test]
    fn status_returns_tuple() {
        let (ok, msg) = cloud_oauth_status();
        assert!(!msg.is_empty());
        let _ = ok;
    }
}
