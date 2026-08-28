//! Port of `kyth_shared.system.updater` — fetch JSON metadata for latest release.

use std::process::Command;
use std::time::Duration;

pub fn updater_available() -> bool {
    // Check if updater binary exists
    std::path::Path::new("/usr/bin/kyth-updater").exists() || std::path::Path::new("/usr/bin/kyth-full-update").exists()
}

fn run_with_timeout(cmd: &[String], timeout: Duration) -> Option<(i32, String)> {
    use std::process::Stdio;
    if cmd.is_empty() { return None; }
    let mut child = Command::new(&cmd[0]).args(&cmd[1..]).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().ok()?;
    let start = std::time::Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(s)) => {
                let out = child.wait_with_output().ok()?;
                return Some((s.code().unwrap_or(-1), String::from_utf8_lossy(&out.stdout).to_string()));
            }
            Ok(None) => {
                if start.elapsed() > timeout { let _ = child.kill(); let _ = child.wait(); return None; }
                std::thread::sleep(Duration::from_millis(50));
            }
            Err(_) => return None,
        }
    }
}

pub fn fetch_updater_metadata() -> Option<String> {
    // Simplified: run updater --check or just return none
    run_with_timeout(&["kyth-updater".to_string(), "--check".to_string()], Duration::from_secs(10)).and_then(|(code, out)| if code==0 { Some(out) } else { None })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn available_bool() { let _ = updater_available(); }
}
