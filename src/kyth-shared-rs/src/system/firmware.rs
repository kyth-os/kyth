//! Port of `kyth_shared.system.firmware` — fwupd helpers.

use std::time::Duration;
use super::runtime_output::count_fwupd_updates;

fn run_with_timeout(cmd: &[String], timeout: Duration) -> Option<(i32, String)> {
    if cmd.is_empty() { return None; }
    let output = super::process::run_bounded(cmd, timeout).ok()?;
    let combined = format!("{}{}", String::from_utf8_lossy(&output.stdout), String::from_utf8_lossy(&output.stderr));
    Some((output.status.code().unwrap_or(-1), combined.trim().to_string()))
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
        Some((0, stdout)) => count_fwupd_updates(&stdout) as i32,
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
