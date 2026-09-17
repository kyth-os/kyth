//! Shared deployment-stamp logic for the two SELinux relabel oneshots
//! (`kyth-selinux-relabel-home`, fast login-critical paths; and
//! `kyth-selinux-relabel-home-full`, the exhaustive background pass).
//!
//! Native port of the `deployment_id` + stamp-file protocol in
//! `build_files/scripts/sysconfig/kyth-selinux-relabel-home{,-full}`.

use std::path::{Path, PathBuf};
use std::time::Duration;

pub const STAMP_DIR: &str = "/var/lib/kyth";

fn run(argv: &[String]) -> Option<String> {
    crate::system::process::run_bounded(argv, Duration::from_secs(60))
        .ok()
        .and_then(|output| {
            output
                .status
                .success()
                .then(|| String::from_utf8_lossy(&output.stdout).into_owned())
        })
}

/// Resolve the current deployment id: `ostree admin status` first, then the
/// `ostree=` kernel cmdline token, then a `fallback-<usr-mtime>` stamp.
/// Mirrors the script's fallbacks, including tolerating a failing ostree.
pub fn deployment_id() -> String {
    if let Some(status) = run(&[
        "ostree".to_string(),
        "admin".to_string(),
        "status".to_string(),
    ]) {
        for line in status.lines() {
            // `* <osname> <checksum>.<serial> ...`
            if let Some(rest) = line.strip_prefix("* ") {
                let mut fields = rest.split_whitespace();
                if let (Some(os), Some(checksum)) = (fields.next(), fields.next()) {
                    return format!("{os} {checksum}");
                }
            }
        }
    }
    if let Ok(cmdline) = std::fs::read_to_string("/proc/cmdline") {
        for token in cmdline.split_whitespace() {
            if let Some(id) = token.strip_prefix("ostree=") {
                return id.to_string();
            }
        }
    }
    let mtime = std::fs::metadata("/usr")
        .and_then(|meta| meta.modified())
        .ok()
        .and_then(|time| time.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|age| age.as_secs())
        .unwrap_or(0);
    format!("fallback-{mtime}")
}

/// True when the stamp file already records this deployment (skip the pass).
pub fn already_done(stamp_dir: &Path, stamp_name: &str, deployment: &str) -> bool {
    std::fs::read_to_string(stamp_dir.join(stamp_name))
        .map(|stamped| stamped == deployment)
        .unwrap_or(false)
}

pub fn write_stamp(stamp_dir: &Path, stamp_name: &str, deployment: &str) {
    let _ = std::fs::create_dir_all(stamp_dir);
    let _ = std::fs::write(stamp_dir.join(stamp_name), deployment);
}

pub fn stamp_dir() -> PathBuf {
    PathBuf::from(STAMP_DIR)
}

pub fn restorecon_forced(paths: &[String]) -> bool {
    let mut argv = vec!["/sbin/restorecon".to_string(), "-F".to_string()];
    argv.extend(paths.iter().cloned());
    run(&argv).is_some()
}

/// Login-critical home paths for one account, mirroring the script's fixed
/// subdir list. Only existing paths are returned.
pub fn login_paths(home: &Path) -> Vec<String> {
    let mut paths = vec![home.to_string_lossy().into_owned()];
    for sub in [".cache", ".config", ".local", ".local/share", ".ssh"] {
        let candidate = home.join(sub);
        if candidate.exists() {
            paths.push(candidate.to_string_lossy().into_owned());
        }
    }
    paths
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_ostree_admin_status() {
        let status = "* fedora-atomic 1a2b3c4d5e.0\n  Version: 44\n";
        let mut found = None;
        for line in status.lines() {
            if let Some(rest) = line.strip_prefix("* ") {
                let mut fields = rest.split_whitespace();
                if let (Some(os), Some(checksum)) = (fields.next(), fields.next()) {
                    found = Some(format!("{os} {checksum}"));
                }
            }
        }
        assert_eq!(found.as_deref(), Some("fedora-atomic 1a2b3c4d5e.0"));
    }

    #[test]
    fn stamp_roundtrip_skips_second_run() {
        let dir = tempfile::tempdir().unwrap();
        assert!(!already_done(dir.path(), "test.stamp", "dep-1"));
        write_stamp(dir.path(), "test.stamp", "dep-1");
        assert!(already_done(dir.path(), "test.stamp", "dep-1"));
        assert!(!already_done(dir.path(), "test.stamp", "dep-2"));
    }

    #[test]
    fn login_paths_only_existing() {
        let dir = tempfile::tempdir().unwrap();
        let home = dir.path().join("alice");
        std::fs::create_dir_all(home.join(".config")).unwrap();
        std::fs::create_dir_all(home.join("Documents")).unwrap();
        let paths = login_paths(&home);
        assert!(paths.iter().any(|path| path == &home.to_string_lossy()));
        assert!(paths.iter().any(|path| path.ends_with(".config")));
        assert!(!paths.iter().any(|path| path.ends_with("Documents")));
    }
}
