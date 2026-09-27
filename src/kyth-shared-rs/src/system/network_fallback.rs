//! Native port of `build_files/scripts/sysconfig/kyth-network-fallback`.
//!
//! Runs when the session may have no connection: if neither ethernet nor
//! wifi is connected after a short wait (and nothing is still connecting),
//! and wifi radio is enabled, open the Plasma network settings so the user
//! can pick a network. Always exits 0; exec-replaces into the settings app
//! when one is available, like the script's `exec`.

use std::time::Duration;

fn nmcli(args: &[&str]) -> Option<String> {
    let argv: Vec<String> = std::iter::once("nmcli".to_string())
        .chain(args.iter().map(|arg| arg.to_string()))
        .collect();
    crate::system::process::run_bounded(&argv, Duration::from_secs(15))
        .ok()
        .and_then(|output| {
            output
                .status
                .success()
                .then(|| String::from_utf8_lossy(&output.stdout).into_owned())
        })
}

fn nmcli_present() -> bool {
    nmcli(&["--version"]).is_some()
}

/// Parse `nmcli -t -f TYPE device status` lines; true when a wifi device exists.
pub fn has_wifi(output: &str) -> bool {
    output.lines().any(|line| line.trim() == "wifi")
}

/// True when an ethernet or wifi device reports `connected`.
pub fn is_connected(output: &str) -> bool {
    output.lines().any(|line| {
        let mut fields = line.split(':');
        matches!(fields.next(), Some("ethernet") | Some("wifi"))
            && fields.next() == Some("connected")
    })
}

/// True when any device reports a `connecting*` state.
pub fn is_connecting(output: &str) -> bool {
    output.lines().any(|line| {
        line.split(':')
            .nth(1)
            .is_some_and(|state| state.starts_with("connecting"))
    })
}

pub fn device_status() -> String {
    nmcli(&["-t", "-f", "TYPE,STATE", "device", "status"]).unwrap_or_default()
}

pub fn wifi_radio_enabled() -> bool {
    nmcli(&["-g", "WIFI", "radio"])
        .map(|state| state.trim().eq_ignore_ascii_case("enabled"))
        .unwrap_or(false)
}

fn command_available(program: &str) -> bool {
    std::env::var_os("PATH")
        .map(|paths| std::env::split_paths(&paths).any(|dir| dir.join(program).is_file()))
        .unwrap_or(false)
}

/// Wait up to ~44s for a connection, then open network settings if wifi is
/// available but unconnected. Returns an argv to exec, or None to exit 0.
pub fn fallback_argv() -> Option<Vec<String>> {
    if !nmcli_present() {
        return None;
    }
    if !has_wifi(&nmcli(&["-t", "-f", "TYPE", "device", "status"]).unwrap_or_default()) {
        return None;
    }
    for _ in 0..22 {
        if is_connected(&device_status()) {
            return None;
        }
        std::thread::sleep(Duration::from_secs(2));
    }
    if is_connecting(&device_status()) {
        return None;
    }
    if !wifi_radio_enabled() {
        return None;
    }
    if command_available("plasmawindowed") {
        return Some(vec![
            "plasmawindowed".to_string(),
            "org.kde.plasma.networkmanagement".to_string(),
        ]);
    }
    if command_available("kcmshell6") {
        return Some(vec![
            "kcmshell6".to_string(),
            "kcm_networkmanagement".to_string(),
        ]);
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_device_tables() {
        let status = "ethernet:unavailable\nwifi:disconnected\nlo:unmanaged\n";
        assert!(has_wifi("ethernet\nwifi\nlo\n"));
        assert!(!has_wifi("ethernet\nlo\n"));
        assert!(!is_connected(status));
        assert!(!is_connecting(status));
        assert!(is_connected("ethernet:connected\nwifi:disconnected\n"));
        assert!(is_connected("wifi:connected\n"));
        assert!(is_connecting(
            "wifi:connecting (getting IP configuration)\n"
        ));
    }
}
