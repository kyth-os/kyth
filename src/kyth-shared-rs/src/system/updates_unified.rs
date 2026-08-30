//! Port of `kyth_shared.system.updates_unified` — bootc + flatpak + firmware.

use std::time::Duration;

fn run_with_timeout(cmd: &str, args: &[&str], timeout: Duration) -> Option<(i32, String)> {
    let mut argv = vec![cmd.to_string()];
    argv.extend(args.iter().map(|arg| (*arg).to_string()));
    let output = super::process::run_bounded(&argv, timeout).ok()?;
    Some((output.status.code().unwrap_or(-1), String::from_utf8_lossy(&output.stdout).to_string()))
}

pub fn pending_updates_summary() -> std::collections::HashMap<String, String> {
    let mut out = std::collections::HashMap::new();
    let firmware = crate::system::firmware::check_firmware_updates(20);
    out.insert("firmware".to_string(), firmware.to_string());
    // flatpak
    let flatpak = run_with_timeout("flatpak", &["remote-ls", "--updates"], Duration::from_secs(15))
        .and_then(|(code, stdout)| if code == 0 { Some(stdout.lines().filter(|l| !l.trim().is_empty()).count().to_string()) } else { Some("0".to_string()) })
        .unwrap_or_else(|| "0".to_string());
    out.insert("flatpak".to_string(), flatpak);
    // bootc
    let bootc = crate::system::bootc_query::fetch_status_data()
        .map(|data| if data.get("status").and_then(|s| s.get("staged")).is_some() { "staged" } else { "current" }.to_string())
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
