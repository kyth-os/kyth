//! Offline backup configuration model.

use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BackupConfig {
    pub repo: String,
    pub btrfs_send: bool,
    pub on_battery: bool,
    pub remote: String,
    /// Opt-in master switch. The `kyth-backup` systemd user timer is
    /// installed but never enabled by the image; scheduled backups only run
    /// after the user sets `enabled = true` and enables the timer.
    pub enabled: bool,
    /// Path to a file holding the restic repository password. Passed as
    /// `restic --password-file`. Empty means the repo is unencrypted or the
    /// password comes from the environment (never from argv).
    pub password_file: String,
    /// Extra args appended to `restic forget` (retention policy, e.g.
    /// `"--keep-daily 7 --keep-weekly 4 --keep-monthly 6"`).
    pub forget_policy: String,
    /// Override for the external-media rule. The default repo lives on the
    /// same disk as `/home`, so a disk loss takes the backup with it;
    /// `validate_repo` refuses that layout unless this is set.
    pub allow_same_disk: bool,
}

/// The historical same-disk default. Kept so existing configs keep parsing,
/// but refused by [`validate_repo`] without an explicit override.
pub const DEFAULT_SAME_DISK_REPO: &str = "/var/cache/kyth/backup";

/// Default `restic forget` retention applied when no policy is configured.
pub const DEFAULT_FORGET_POLICY: &str = "--keep-daily 7 --keep-weekly 4 --keep-monthly 6";

impl Default for BackupConfig {
    fn default() -> Self {
        Self {
            repo: DEFAULT_SAME_DISK_REPO.into(),
            btrfs_send: false,
            on_battery: false,
            remote: String::new(),
            enabled: false,
            password_file: String::new(),
            forget_policy: DEFAULT_FORGET_POLICY.into(),
            allow_same_disk: false,
        }
    }
}

pub fn config_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path {
        return path.as_ref().to_path_buf();
    }
    if std::env::var("KYTH_TEST_MODE").ok().as_deref() == Some("1") {
        if let Some(config) = std::env::var_os("XDG_CONFIG_HOME") {
            return PathBuf::from(config).join("kyth/backup.toml");
        }
    }
    PathBuf::from("/etc/kyth/backup.toml")
}

pub fn load(path: impl AsRef<Path>) -> BackupConfig {
    let Ok(raw) = std::fs::read_to_string(path) else {
        return BackupConfig::default();
    };
    let Ok(value) = raw.parse::<toml::Value>() else {
        return BackupConfig::default();
    };
    let table = value.as_table();
    let bool_key = |key: &str, fallback: bool| {
        table
            .and_then(|table| table.get(key))
            .and_then(toml::Value::as_bool)
            .unwrap_or(fallback)
    };
    let str_key = |key: &str, fallback: &str| {
        table
            .and_then(|table| table.get(key))
            .and_then(toml::Value::as_str)
            .unwrap_or(fallback)
            .to_string()
    };
    BackupConfig {
        repo: str_key("repo", DEFAULT_SAME_DISK_REPO),
        btrfs_send: bool_key("btrfs_send", false),
        on_battery: bool_key("on_battery", false),
        remote: str_key("remote", ""),
        enabled: bool_key("enabled", false),
        password_file: str_key("password_file", ""),
        forget_policy: str_key("forget_policy", DEFAULT_FORGET_POLICY),
        allow_same_disk: bool_key("allow_same_disk", false),
    }
}

/// True when any battery reports `Discharging`, mirroring the launcher
/// helper. Unreadable files are skipped.
pub fn on_battery_in(root: &Path) -> bool {
    let Ok(entries) = std::fs::read_dir(root) else {
        return false;
    };
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        if !name.starts_with("BAT") {
            continue;
        }
        if let Ok(status) = std::fs::read_to_string(entry.path().join("status")) {
            if status.trim() == "Discharging" {
                return true;
            }
        }
    }
    false
}

pub fn on_battery() -> bool {
    on_battery_in(Path::new("/sys/class/power_supply"))
}

pub fn save(path: impl AsRef<Path>, config: &BackupConfig) -> std::io::Result<()> {
    let text = format!(
        "# Kyth backup full /home — opt-in: set enabled = true and\n# `systemctl --user enable --now kyth-backup.timer` to schedule.\n# Point repo at EXTERNAL media (e.g. /run/media/$USER/BACKUP/restic);\n# the same-disk default is refused unless allow_same_disk = true.\nrepo = {:?}\nbtrfs_send = {}\non_battery = {}\nremote = {:?}\nenabled = {}\npassword_file = {:?}\nforget_policy = {:?}\nallow_same_disk = {}\n",
        config.repo,
        config.btrfs_send,
        config.on_battery,
        config.remote,
        config.enabled,
        config.password_file,
        config.forget_policy,
        config.allow_same_disk,
    );
    crate::atomic_io::atomic_write_text(path, &text, Some(0o600))
}

/// True when `repo` sits on external media: under one of the given external
/// mount points (`/run/media/...`, `/mnt/...`). Pure over an explicit mount
/// list so it is unit-testable; [`repo_on_external_mount`] reads the live
/// mount table.
pub fn repo_is_external(repo: &str, external_mounts: &[&str]) -> bool {
    let repo = repo.trim_end_matches('/');
    if repo.is_empty() || repo == "/" {
        return false;
    }
    external_mounts.iter().any(|mount| {
        let mount = mount.trim_end_matches('/');
        !mount.is_empty() && (repo == mount || repo.starts_with(&format!("{mount}/")))
    })
}

/// External mount points from `/proc/mounts`: removable-media and explicit
/// admin mounts only. The root filesystem is deliberately excluded — a repo
/// under `/var`, `/home`, or any same-disk path is NOT external.
pub fn external_mounts_from_proc_mounts(text: &str) -> Vec<String> {
    let mut mounts = Vec::new();
    for line in text.lines() {
        let fields: Vec<&str> = line.split_whitespace().collect();
        let Some(target) = fields.get(1).copied() else {
            continue;
        };
        if target == "/" {
            continue;
        }
        if target.starts_with("/run/media/") || target.starts_with("/mnt/") {
            if !mounts.iter().any(|seen| seen == target) {
                mounts.push(target.to_string());
            }
        }
    }
    mounts
}

/// Refuse the foot-gun layout: a repo on the same disk as the data it backs
/// up (the historical `/var/cache/kyth/backup` default or anything that is
/// not on external media) unless the user recorded `allow_same_disk = true`.
pub fn validate_repo(config: &BackupConfig, external_mounts: &[&str]) -> Result<(), String> {
    if config.repo.trim().is_empty() {
        return Err("backup repo is empty; point repo at external media.".to_string());
    }
    if repo_is_external(&config.repo, external_mounts) {
        return Ok(());
    }
    if config.allow_same_disk {
        return Ok(());
    }
    Err(format!(
        "backup repo {:?} is not on external media (/run/media/…, /mnt/…); \
a same-disk repo dies with the disk it backs up. Point repo at external \
media or set allow_same_disk = true to override.",
        config.repo
    ))
}

/// Shared `--repo` / `--password-file` prefix for every restic invocation.
/// The password travels via file (or not at all), never via argv.
pub fn restic_prefix(config: &BackupConfig) -> Vec<String> {
    let mut argv = vec![
        "restic".to_string(),
        "--repo".to_string(),
        config.repo.clone(),
    ];
    if !config.password_file.trim().is_empty() {
        argv.push("--password-file".to_string());
        argv.push(config.password_file.clone());
    }
    argv
}

/// `restic backup` of `source` (usually `$HOME`).
pub fn backup_argv(config: &BackupConfig, source: &str) -> Vec<String> {
    let mut argv = restic_prefix(config);
    argv.push("backup".to_string());
    argv.push(source.to_string());
    argv
}

/// `restic forget` retention pass. The policy defaults to
/// [`DEFAULT_FORGET_POLICY`] so snapshots do not grow without bound.
pub fn forget_argv(config: &BackupConfig) -> Vec<String> {
    let mut argv = restic_prefix(config);
    argv.extend(["forget".to_string(), "--prune".to_string()]);
    argv.extend(config.forget_policy.split_whitespace().map(str::to_string));
    argv
}

/// `restic check` integrity pass after backup + forget.
pub fn check_argv(config: &BackupConfig) -> Vec<String> {
    let mut argv = restic_prefix(config);
    argv.push("check".to_string());
    argv
}

/// Flags allowed in `forget_policy`. Anything else (notably `--repo`,
/// `--password-file`, or shell metacharacters) is rejected by
/// [`validate_forget_policy`] so a malformed config cannot turn
/// `restic forget --prune` into unexpected retention or credential exposure.
pub const FORGET_FLAG_ALLOWLIST: &[&str] = &[
    "--keep-last",
    "--keep-hourly",
    "--keep-daily",
    "--keep-weekly",
    "--keep-monthly",
    "--keep-yearly",
    "--keep-within",
    "--keep-tag",
    "--group-by",
    "--prune",
];

/// Validate a `forget_policy` string before it is `split_whitespace`-appended
/// to the restic forget argv. Fails closed on unknown flags, flag-like values
/// (a missing value would re-target the next token), and shell metacharacters.
pub fn validate_forget_policy(policy: &str) -> Result<(), String> {
    let mut expect_value_for: Option<&str> = None;
    let mut seen_any = false;
    for token in policy.split_whitespace() {
        if let Some(flag) = expect_value_for.take() {
            if token.starts_with('-') || token.contains(char::is_whitespace) {
                return Err(format!(
                    "backup forget_policy: {flag} needs a value, got {token:?}."
                ));
            }
            if token.contains([
                ';', '&', '|', '$', '`', '(', ')', '<', '>', '\\', '"', '\'', '!',
            ]) {
                return Err(format!(
                    "backup forget_policy: value {token:?} for {flag} contains unsafe characters."
                ));
            }
            seen_any = true;
            continue;
        }
        if !FORGET_FLAG_ALLOWLIST.contains(&token) {
            return Err(format!(
                "backup forget_policy: unsupported flag {token:?}; allowed: {}.",
                FORGET_FLAG_ALLOWLIST.join(" ")
            ));
        }
        seen_any = true;
        // `--prune` is standalone; every other allowed flag takes a value.
        if token != "--prune" {
            expect_value_for = Some(token);
        }
    }
    if let Some(flag) = expect_value_for {
        return Err(format!(
            "backup forget_policy: {flag} needs a value, got end of policy."
        ));
    }
    if !seen_any {
        // Empty policy: forget runs as bare `forget --prune` with no
        // retention bounds. Allowed (explicit opt-out), not an error.
    }
    Ok(())
}

/// True when a restic repo at `repo` already holds at least one snapshot.
///
/// Guards the `rclone sync repo remote` mirror stage: syncing a fresh-empty
/// repo over a populated remote deletes every remote snapshot. A fresh
/// `restic init` leaves `snapshots/` empty, so a missing or empty
/// `snapshots/` dir means "nothing to upload — do not mirror".
pub fn repo_has_snapshots(repo: &std::path::Path) -> bool {
    let mut entries = match std::fs::read_dir(repo.join("snapshots")) {
        Ok(entries) => entries,
        Err(_) => return false,
    };
    entries.any(|entry| entry.map(|entry| entry.path().is_file()).unwrap_or(false))
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn detects_discharging_batteries() {
        let directory = tempdir().unwrap();
        let root = directory.path().join("power_supply");
        std::fs::create_dir_all(root.join("BAT0")).unwrap();
        std::fs::create_dir_all(root.join("AC")).unwrap();
        std::fs::write(root.join("BAT0/status"), "Discharging\n").unwrap();
        assert!(on_battery_in(&root));
        std::fs::write(root.join("BAT0/status"), "Charging\n").unwrap();
        assert!(!on_battery_in(&root));
        assert!(!on_battery_in(&directory.path().join("missing")));
    }

    #[test]
    fn round_trips_backup_config() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("backup.toml");
        let config = BackupConfig {
            repo: "/mnt/backup".into(),
            btrfs_send: true,
            on_battery: true,
            remote: "nas".into(),
            enabled: true,
            password_file: "/run/media/user/BACKUP/restic-pass".into(),
            forget_policy: "--keep-daily 3".into(),
            allow_same_disk: false,
        };
        save(&path, &config).unwrap();
        assert_eq!(load(&path), config);
    }

    #[test]
    fn new_keys_default_to_opt_in_off() {
        let directory = tempdir().unwrap();
        let missing = directory.path().join("missing.toml");
        let config = load(&missing);
        assert!(!config.enabled);
        assert!(config.password_file.is_empty());
        assert_eq!(config.forget_policy, DEFAULT_FORGET_POLICY);
        assert!(!config.allow_same_disk);
        // Legacy files without the new keys keep parsing with safe defaults.
        let legacy = directory.path().join("legacy.toml");
        std::fs::write(&legacy, "repo = \"/mnt/usb/restic\"\nbtrfs_send = true\n").unwrap();
        let loaded = load(&legacy);
        assert_eq!(loaded.repo, "/mnt/usb/restic");
        assert!(loaded.btrfs_send);
        assert!(!loaded.enabled);
    }

    #[test]
    fn refuses_same_disk_repo_without_override() {
        let mounts = ["/run/media/alice/BACKUP", "/mnt/nas"];
        let external = BackupConfig {
            repo: "/run/media/alice/BACKUP/restic".into(),
            ..BackupConfig::default()
        };
        assert!(validate_repo(&external, &mounts).is_ok());
        let same_disk = BackupConfig::default();
        let error = validate_repo(&same_disk, &mounts).expect_err("same-disk default must fail");
        assert!(error.contains("external media"));
        assert!(error.contains("allow_same_disk"));
        let overridden = BackupConfig {
            allow_same_disk: true,
            ..BackupConfig::default()
        };
        assert!(validate_repo(&overridden, &mounts).is_ok());
        // A sibling of an external mount is not on it.
        let sneaky = BackupConfig {
            repo: "/run/media-fake/restic".into(),
            ..BackupConfig::default()
        };
        assert!(validate_repo(&sneaky, &mounts).is_err());
    }

    #[test]
    fn parses_external_mounts_without_root() {
        let mounts = external_mounts_from_proc_mounts(
            "/dev/sda2 / btrfs rw 0 0\n/dev/sdb1 /run/media/alice/BACKUP exfat rw 0 0\nnas:/share /mnt/nas nfs rw 0 0\n",
        );
        assert_eq!(mounts, vec!["/run/media/alice/BACKUP", "/mnt/nas"]);
        assert!(!mounts.iter().any(|mount| mount == "/"));
    }

    #[test]
    fn forget_policy_allows_only_known_keep_flags() {
        assert!(validate_forget_policy("--keep-daily 7 --keep-weekly 4 --keep-monthly 6").is_ok());
        assert!(validate_forget_policy("--keep-last 3 --prune").is_ok());
        assert!(validate_forget_policy("").is_ok());
        // Unknown flags (notably repo/password overrides) fail closed.
        assert!(validate_forget_policy("--keep-daily 7 --repo /tmp/evil").is_err());
        assert!(validate_forget_policy("--password-file /tmp/p").is_err());
        assert!(validate_forget_policy("--prune --verbose").is_err());
        // A missing value must not re-target the next token as a value.
        assert!(validate_forget_policy("--keep-daily --keep-weekly 4").is_err());
        assert!(validate_forget_policy("--keep-daily").is_err());
        // Shell metacharacters in values are rejected.
        assert!(validate_forget_policy("--keep-tag a;b").is_err());
        assert!(validate_forget_policy("--keep-tag $(x)").is_err());
        assert!(validate_forget_policy("--group-by host --keep-last 5").is_ok());
    }

    #[test]
    fn repo_without_snapshots_is_not_mirrorable() {
        let directory = tempdir().unwrap();
        let repo = directory.path().join("restic");
        // Missing entirely: nothing to upload.
        assert!(!repo_has_snapshots(&repo));
        // Fresh `restic init` layout: empty snapshots/ dir.
        std::fs::create_dir_all(repo.join("snapshots")).unwrap();
        assert!(!repo_has_snapshots(&repo));
        // One snapshot file: safe to mirror.
        std::fs::write(repo.join("snapshots").join("abc123"), [0u8; 8]).unwrap();
        assert!(repo_has_snapshots(&repo));
    }

    #[test]
    fn restic_argv_uses_password_file_forget_and_check() {
        let config = BackupConfig {
            repo: "/run/media/alice/BACKUP/restic".into(),
            password_file: "/etc/kyth/restic-pass".into(),
            ..BackupConfig::default()
        };
        let backup = backup_argv(&config, "/home/alice");
        assert_eq!(
            backup,
            vec![
                "restic",
                "--repo",
                "/run/media/alice/BACKUP/restic",
                "--password-file",
                "/etc/kyth/restic-pass",
                "backup",
                "/home/alice"
            ]
        );
        let forget = forget_argv(&config);
        assert!(forget.windows(2).any(|pair| pair == ["forget", "--prune"]));
        assert!(forget.iter().any(|arg| arg == "--keep-daily"));
        // No secret material on the command line: only the file path.
        assert!(!forget
            .iter()
            .any(|arg| arg.contains("password") && !arg.contains("password-file")));
        let check = check_argv(&config);
        assert_eq!(check.last().map(String::as_str), Some("check"));
        let no_password = BackupConfig::default();
        assert!(!restic_prefix(&no_password)
            .iter()
            .any(|arg| arg == "--password-file"));
    }
}
