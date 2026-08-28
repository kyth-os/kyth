//! Port of `kyth_shared.system.firmware` — fwupd helpers.

use std::process::Command;
use std::time::Duration;

fn run_with_timeout(cmd: &[String], timeout: Duration) -> Option<(i32, String)> {
    use std::process::Stdio;
    if cmd.is_empty() { return None; }
    let mut child = Command::new(&cmd[0]).args(&cmd[1..]).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().ok()?;
    let start = std::time::Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(s)) => {
                let out = child.wait_with_output().ok()?;
                let combined = format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
                return Some((s.code().unwrap_or(-1), combined.trim().to_string()));
            }
            Ok(None) => {
                if start.elapsed() > timeout { let _ = child.kill(); let _ = child.wait(); return None; }
                std::thread::sleep(Duration::from_millis(50));
            }
            Err(_) => return None,
        }
    }
}

pub fn firmware_refresh_commands() -> Vec<Vec<String>> {
    vec![vec!["fwupdmgr".to_string(), "refresh".to_string(), "--force".to_string()]]
}
pub fn firmware_devices_command() -> Vec<String> { vec!["fwupdmgr".to_string(), "get-devices".to_string()] }
pub fn firmware_updates_command() -> Vec<String> { vec!["fwupdmgr".to_string(), "get-updates".to_string()] }
pub fn firmware_update_command() -> Vec<String> { vec!["fwupdmgr".to_string(), "update".to_string(), "--assume-yes".to_string(), "--no-reboot-check".to_string()] }

pub fn run_firmware_refresh(timeout: u64) -> (bool, String) {
    let cmd = firmware_refresh_commands()[0].clone();
    match run_with_timeout(&cmd, Duration::from_secs(timeout)) {
        Some((0, out)) => (true, out),
        Some((_, out)) if !out.is_empty() => (false, out),
        Some((_, _)) => (false, "".to_string()),
        None => (false, format!("fwupdmgr refresh timed out after {}s", timeout)),
    }
}

pub fn check_firmware_updates(timeout: u64) -> i32 {
    let cmd = firmware_updates_command();
    match run_with_timeout(&cmd, Duration::from_secs(timeout)) {
        Some((2, _)) => 0,
        Some((0, stdout)) if stdout.trim().is_empty() => 0,
        Some((0, stdout)) => {
            // count_fwupd_updates from runtime_output: count lines with "Update" or devices
            // Simplified: count occurrences of "Version:" or "Update" ?
            stdout.lines().filter(|l| l.to_lowercase().contains("update") || l.contains("Version:")).count() as i32
        }
        _ => 0,
    }
}

pub fn run_firmware_update(timeout: u64) -> (bool, String) {
    let cmd = firmware_update_command();
    match run_with_timeout(&cmd, Duration::from_secs(timeout)) {
        Some((0, out)) => (true, out),
        Some((_, out)) => (false, out),
        None => (false, format!("fwupdmgr update timed out after {}s", timeout)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn commands() {
        assert_eq!(firmware_devices_command(), vec!["fwupdmgr","get-devices"]);
        assert_eq!(firmware_updates_command(), vec!["fwupdmgr","get-updates"]);
    }
}
