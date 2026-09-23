//! Port of `kyth_shared.system.smb` — Aurora autodiscover parity (N33).
//! avahi-browse / smbclient discovery + gio mount, no auto-mount on boot.

use std::time::Duration;

/// Hostnames accepted for SMB discovery: a conservative allowlist (letters,
/// digits, dot, dash, underscore, max 253) that also rejects a leading dash
/// so the value can never parse as an smbclient flag.
pub fn is_valid_smb_host(host: &str) -> bool {
    !host.is_empty()
        && host.len() <= 253
        && !host.starts_with('-')
        && host
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'-' | b'_'))
}

pub fn smb_discover_command(host: Option<&str>) -> Vec<String> {
    if let Some(h) = host {
        vec![
            "smbclient".to_string(),
            "-L".to_string(),
            "-N".to_string(),
            "--".to_string(),
            h.to_string(),
        ]
    } else {
        vec![
            "avahi-browse".to_string(),
            "-r".to_string(),
            "_smb._tcp".to_string(),
        ]
    }
}

pub fn smb_mount_command(share: &str) -> Vec<String> {
    vec!["gio".to_string(), "mount".to_string(), share.to_string()]
}

/// Display form of an SMB URI with userinfo stripped: `smb://user:pass@host/share`
/// becomes `smb://host/share`. Status strings reach the UI and logs, so the
/// raw URI (which may carry a password) must never be echoed.
pub fn redact_smb_uri(share: &str) -> String {
    let Some(rest) = share.strip_prefix("smb://") else {
        return "smb://…".to_string();
    };
    let after_authority = rest.find('/').map(|index| &rest[index..]).unwrap_or("");
    let authority = &rest[..rest.len() - after_authority.len()];
    let host = authority.rsplit('@').next().unwrap_or(authority);
    format!("smb://{host}{after_authority}")
}

/// True when the URI's authority carries userinfo (`user[:pass]@`).
/// Such URIs must never be spawned: the child argv is world-readable via
/// /proc/<pid>/cmdline for the whole (up to 30s) mount. Credentials go
/// through gio's keyring prompt instead.
pub fn smb_uri_has_userinfo(share: &str) -> bool {
    let rest = share.strip_prefix("smb://").unwrap_or(share);
    let authority = rest.split('/').next().unwrap_or("");
    authority.contains('@')
}

fn run_with_timeout(cmd: &[String], timeout: Duration) -> Option<(i32, String, String)> {
    if cmd.is_empty() {
        return None;
    }
    let output = super::process::run_bounded(cmd, timeout).ok()?;
    Some((
        output.status.code().unwrap_or(-1),
        String::from_utf8_lossy(&output.stdout).to_string(),
        String::from_utf8_lossy(&output.stderr).to_string(),
    ))
}

pub fn smb_browse_dry_run(host: Option<&str>) -> (bool, String) {
    if let Some(host) = host {
        if !is_valid_smb_host(host) {
            return (false, "invalid SMB host".to_string());
        }
    }
    let cmd = smb_discover_command(host);
    match run_with_timeout(&cmd, Duration::from_secs(10)) {
        Some((0, stdout, _)) => (true, stdout.chars().take(500).collect()),
        Some((_, _, stderr)) if !stderr.is_empty() => (false, stderr.chars().take(500).collect()),
        Some((_, _, _)) => (false, format!("{} failed", cmd.join(" "))),
        None => {
            // distinguish not-installed
            let help = vec![cmd[0].clone(), "--help".into()];
            let exists = super::process::run_bounded(&help, Duration::from_secs(3)).is_ok();
            if !exists {
                (false, format!("{} not installed", cmd[0]))
            } else {
                (false, "timeout".to_string())
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn redact_strips_userinfo_but_keeps_host_and_share() {
        assert_eq!(
            redact_smb_uri("smb://user:s3cret@nas/share"),
            "smb://nas/share"
        );
        assert_eq!(redact_smb_uri("smb://nas/share"), "smb://nas/share");
        assert_eq!(redact_smb_uri("smb://nas"), "smb://nas");
    }
    #[test]
    fn userinfo_detection_blocks_credential_uris_only() {
        assert!(smb_uri_has_userinfo("smb://user:s3cret@nas/share"));
        assert!(smb_uri_has_userinfo("smb://user@nas/share"));
        assert!(!smb_uri_has_userinfo("smb://nas/share"));
        assert!(!smb_uri_has_userinfo("smb://nas"));
        // An @ in the share path is not userinfo.
        assert!(!smb_uri_has_userinfo("smb://nas/team@share"));
    }
    #[test]
    fn discover_no_host() {
        assert_eq!(
            smb_discover_command(None),
            vec!["avahi-browse", "-r", "_smb._tcp"]
        );
    }
    #[test]
    fn discover_host() {
        assert_eq!(
            smb_discover_command(Some("host")),
            vec!["smbclient", "-L", "-N", "--", "host"]
        );
    }
    #[test]
    fn host_allowlist_rejects_flags_and_separates_positional() {
        assert!(is_valid_smb_host("fileserver-01.example"));
        assert!(is_valid_smb_host("192.168.1.10"));
        assert!(!is_valid_smb_host("-evil"));
        assert!(!is_valid_smb_host("--help"));
        assert!(!is_valid_smb_host("host; rm -rf /"));
        assert!(!is_valid_smb_host(""));
        let cmd = smb_discover_command(Some("fileserver"));
        let dash = cmd
            .iter()
            .position(|arg| arg == "--")
            .expect("host needs a -- separator");
        assert_eq!(cmd[dash + 1], "fileserver");
        assert_eq!(
            smb_browse_dry_run(Some("-evil")),
            (false, "invalid SMB host".to_string())
        );
    }
    #[test]
    fn mount() {
        assert_eq!(
            smb_mount_command("smb://host/share"),
            vec!["gio", "mount", "smb://host/share"]
        );
    }
}
