//! Native port of `build_files/scripts/sysconfig/kyth-enable-bluetooth`.
//!
//! Boot oneshot: clear stale rfkill persistence for bluetooth, unblock the
//! bluetooth radio, restore a pre-existing wifi soft-block, and power the
//! adapter on. Every step is best-effort; the binary always exits 0 so a
//! missing radio stack can never fail the boot.

use std::path::Path;
use std::time::Duration;

pub fn rfkill_dir() -> &'static str {
    "/var/lib/systemd/rfkill"
}

fn run_best_effort(argv: &[String]) {
    let _ = crate::system::process::run_bounded(argv, Duration::from_secs(15));
}

/// Parse `rfkill list wifi` output for a wifi soft block.
pub fn wifi_soft_blocked(output: &str) -> bool {
    output.contains("Soft blocked: yes")
}

pub fn wifi_was_soft_blocked() -> bool {
    crate::system::process::run_bounded(
        &["rfkill".to_string(), "list".to_string(), "wifi".to_string()],
        Duration::from_secs(15),
    )
    .map(|output| wifi_soft_blocked(&String::from_utf8_lossy(&output.stdout)))
    .unwrap_or(false)
}

fn command_available(program: &str) -> bool {
    // `command -v` is a shell builtin, not an executable: search PATH directly.
    std::env::var_os("PATH")
        .map(|paths| std::env::split_paths(&paths).any(|dir| dir.join(program).is_file()))
        .unwrap_or(false)
}

/// Clear stale rfkill state files matching `*bluetooth*`. Returns the count
/// removed; errors are ignored like the script's `|| true`.
pub fn clear_stale_rfkill(dir: &Path) -> usize {
    let entries = std::fs::read_dir(dir).map(|entries| entries.collect::<Vec<_>>());
    let mut removed = 0;
    for entry in entries.into_iter().flatten().flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        if name.contains("bluetooth") && std::fs::remove_file(entry.path()).is_ok() {
            removed += 1;
        }
    }
    removed
}

pub fn enable() {
    let _ = clear_stale_rfkill(Path::new(rfkill_dir()));
    let wifi_blocked = wifi_was_soft_blocked();
    if command_available("rfkill") {
        run_best_effort(&[
            "rfkill".to_string(),
            "unblock".to_string(),
            "bluetooth".to_string(),
        ]);
        if wifi_blocked {
            run_best_effort(&[
                "rfkill".to_string(),
                "block".to_string(),
                "wifi".to_string(),
            ]);
        }
    }
    if command_available("bluetoothctl") {
        run_best_effort(&[
            "bluetoothctl".to_string(),
            "power".to_string(),
            "on".to_string(),
        ]);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn detects_wifi_soft_block() {
        assert!(wifi_soft_blocked(
            "1: phy0: Wireless LAN\n\tSoft blocked: yes\n\tHard blocked: no\n"
        ));
        assert!(!wifi_soft_blocked(
            "1: phy0: Wireless LAN\n\tSoft blocked: no\n\tHard blocked: no\n"
        ));
        assert!(!wifi_soft_blocked(""));
    }

    #[test]
    fn clears_only_bluetooth_state() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(dir.path().join("0-bluetooth"), "").unwrap();
        fs::write(dir.path().join("1-wlan"), "").unwrap();
        fs::write(dir.path().join("readme.txt"), "").unwrap();
        assert_eq!(clear_stale_rfkill(dir.path()), 1);
        assert!(!dir.path().join("0-bluetooth").exists());
        assert!(dir.path().join("1-wlan").exists());
        assert!(dir.path().join("readme.txt").exists());
    }
}
