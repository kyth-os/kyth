//! Shared stamp logic for two SELinux relabel oneshots. The login-critical
//! subset remains keyed to the deployment id; the exhaustive background pass
//! is keyed to active file-context policy content to avoid needless full-home
//! walks after every deployment.
//!
//! The retained shell fixtures under `build_files/scripts/sysconfig` mirror
//! the same intent; the native binaries are installed in production.

use sha2::{Digest, Sha256};
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

fn selinux_type_from_config(contents: &str) -> Option<String> {
    for line in contents.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        if key.trim() != "SELINUXTYPE" {
            continue;
        }
        let value = value.trim().trim_matches(['"', '\'']);
        if value.is_empty()
            || !value
                .chars()
                .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '_' | '-' | '.'))
        {
            return None;
        }
        return Some(value.to_string());
    }
    None
}

/// Hash the active policy's file-context inputs in a deterministic order.
/// On any read error or missing input, return `None` so callers fall back to
/// the deployment stamp rather than incorrectly skipping a relabel.
pub fn file_contexts_fingerprint_in(contexts_dir: &Path) -> Option<String> {
    let mut paths = Vec::new();
    for entry in std::fs::read_dir(contexts_dir).ok()? {
        let entry = entry.ok()?;
        let path = entry.path();
        let name = path.file_name()?.to_string_lossy();
        if !name.starts_with("file_contexts") {
            continue;
        }
        if !entry.metadata().ok()?.is_file() {
            continue;
        }
        paths.push(path);
    }
    paths.sort();
    if paths.is_empty() {
        return None;
    }

    let mut hasher = Sha256::new();
    for path in paths {
        let name = path.file_name()?.to_string_lossy();
        let content = std::fs::read(&path).ok()?;
        hasher.update(name.as_bytes());
        hasher.update([0]);
        hasher.update(content);
    }
    Some(format!("{:x}", hasher.finalize()))
}

/// Current active SELinux file-context policy fingerprint, if it is readable.
pub fn active_file_contexts_fingerprint() -> Option<String> {
    let config = std::fs::read_to_string("/etc/selinux/config").ok()?;
    let selinux_type = selinux_type_from_config(&config)?;
    let contexts_dir = Path::new("/etc/selinux")
        .join(selinux_type)
        .join("contexts/files");
    file_contexts_fingerprint_in(&contexts_dir)
}

/// Full relabels are keyed to policy content, so a new deployment with the
/// same labeling rules does not trigger another enormous `/var/home` walk.
/// If policy cannot be measured, stay conservative and key by deployment.
pub fn full_relabel_stamp(policy_fingerprint: Option<&str>, deployment: &str) -> String {
    match policy_fingerprint {
        Some(fingerprint) => format!("selinux-file-contexts-sha256:{fingerprint}"),
        None => format!("deployment:{deployment}"),
    }
}

/// True when the stamp file already records this relabel key (skip the pass).
pub fn already_done(stamp_dir: &Path, stamp_name: &str, stamp_value: &str) -> bool {
    std::fs::read_to_string(stamp_dir.join(stamp_name))
        .map(|stamped| stamped == stamp_value)
        .unwrap_or(false)
}

pub fn write_stamp(stamp_dir: &Path, stamp_name: &str, stamp_value: &str) {
    let _ = std::fs::create_dir_all(stamp_dir);
    let _ = std::fs::write(stamp_dir.join(stamp_name), stamp_value);
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

/// Rootless podman overlay layer dirs under each `$home`. `restorecon -D`
/// writes `security.sehash` on every directory it visits; overlayfs copy-up
/// of those dirs in a user namespace returns EPERM, which breaks dnf/apt
/// inside distrobox/toolbox. The full-home walk must exclude these.
pub fn overlay_exclude_paths(home_root: &Path) -> Vec<PathBuf> {
    let mut out = Vec::new();
    let Ok(homes) = std::fs::read_dir(home_root) else {
        return out;
    };
    for home in homes.flatten() {
        let path = home.path();
        if !path.is_dir() {
            continue;
        }
        let overlay = path.join(".local/share/containers/storage/overlay");
        if overlay.is_dir() {
            out.push(overlay);
        }
    }
    out.sort();
    out
}

/// `restorecon -RF -D -T0 [-e overlay...] <home_root>`
pub fn full_restorecon_argv(home_root: &Path) -> Vec<String> {
    let mut argv = vec![
        "/sbin/restorecon".to_string(),
        "-RF".to_string(),
        "-D".to_string(),
        "-T0".to_string(),
    ];
    for overlay in overlay_exclude_paths(home_root) {
        argv.push("-e".to_string());
        argv.push(overlay.to_string_lossy().into_owned());
    }
    argv.push(home_root.display().to_string());
    argv
}

/// Strip leftover `security.sehash` digests from overlay layers that a
/// previous un-excluded `restorecon -D` already labeled.
pub fn overlay_sehash_cleanup_argv(overlay: &Path) -> Vec<String> {
    vec![
        "/usr/bin/restorecon_xattr".to_string(),
        "-rD".to_string(),
        overlay.to_string_lossy().into_owned(),
    ]
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
    fn parses_active_selinux_type_safely() {
        assert_eq!(
            selinux_type_from_config("# policy\nSELINUXTYPE=targeted\n"),
            Some("targeted".into())
        );
        assert_eq!(selinux_type_from_config("SELINUXTYPE=../targeted"), None);
    }

    #[test]
    fn file_contexts_fingerprint_changes_with_policy_content() {
        let dir = tempfile::tempdir().unwrap();
        let source = dir.path().join("file_contexts");
        let compiled = dir.path().join("file_contexts.bin");
        std::fs::write(&source, "home labels v1").unwrap();
        std::fs::write(&compiled, "compiled v1").unwrap();
        let first = file_contexts_fingerprint_in(dir.path()).unwrap();
        assert_eq!(first, file_contexts_fingerprint_in(dir.path()).unwrap());

        std::fs::write(&source, "home labels v2").unwrap();
        let second = file_contexts_fingerprint_in(dir.path()).unwrap();
        assert_ne!(first, second);
    }

    #[test]
    fn full_stamp_ignores_deployment_but_tracks_policy() {
        let first = full_relabel_stamp(Some("policy-a"), "deployment-1");
        assert_eq!(first, full_relabel_stamp(Some("policy-a"), "deployment-2"));
        assert_ne!(first, full_relabel_stamp(Some("policy-b"), "deployment-2"));
        assert_ne!(
            full_relabel_stamp(None, "deployment-1"),
            full_relabel_stamp(None, "deployment-2")
        );
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

    #[test]
    fn overlay_exclude_paths_skips_homes_without_container_storage() {
        let dir = tempfile::tempdir().unwrap();
        let alice = dir.path().join("alice");
        std::fs::create_dir_all(alice.join(".config")).unwrap();
        assert!(overlay_exclude_paths(dir.path()).is_empty());
    }

    #[test]
    fn full_restorecon_argv_excludes_rootless_overlay_layers() {
        // restorecon -D writes security.sehash on every directory it walks.
        // Overlayfs copy-up of those dirs in a rootless userns returns EPERM,
        // so dnf/apt inside distrobox cannot replace image-layer files.
        let dir = tempfile::tempdir().unwrap();
        let overlay = dir
            .path()
            .join("alice/.local/share/containers/storage/overlay");
        std::fs::create_dir_all(&overlay).unwrap();
        std::fs::create_dir_all(dir.path().join("bob/Documents")).unwrap();
        let argv = full_restorecon_argv(dir.path());
        assert_eq!(argv[0], "/sbin/restorecon");
        assert!(argv
            .windows(2)
            .any(|pair| { pair[0] == "-e" && pair[1] == overlay.to_string_lossy() }));
        assert_eq!(
            argv.last().map(String::as_str),
            Some(dir.path().to_str().unwrap())
        );
        assert!(!argv
            .windows(2)
            .any(|pair| { pair[0] == "-e" && pair[1].contains("bob") }));
    }
}
