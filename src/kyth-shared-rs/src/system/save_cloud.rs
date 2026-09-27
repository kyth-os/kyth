//! Offline per-game save-cloud configuration.
//!
//! This ports the config model from `kyth_shared.save_cloud`. Restic/rclone
//! execution and save discovery remain explicit caller-owned operations.

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

pub const DEFAULT_REPO: &str = "/var/cache/kyth/saves";

/// Warn before bundling a Flatpak app-data tree larger than this: a full
/// `~/.var/app` copy can silently add tens of GiB (shaders, caches) to a
/// transfer/save bundle. Callers surface the warning and require opt-in.
pub const FLATPAK_DATA_WARN_BYTES: u64 = 10 * 1024 * 1024 * 1024;

/// Default restic include set for `kyth-save-sync`: Steam compat prefixes
/// (native + Flatpak) plus the small Kyth state dirs. Everything else is
/// opt-in so a first backup never vacuums `~/.var/app` caches by accident.
pub const DEFAULT_RESTIC_INCLUDES: &[&str] = &[
    ".local/share/Steam/steamapps/compatdata",
    ".var/app/com.valvesoftware.Steam/data/Steam/steamapps/compatdata",
    ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/compatdata",
    ".config/kyth",
    ".local/share/kyth",
];

/// Default include globs, joined to `home`. Only existing paths are returned.
pub fn default_restic_includes(home: &Path) -> Vec<PathBuf> {
    DEFAULT_RESTIC_INCLUDES
        .iter()
        .map(|rel| home.join(rel))
        .filter(|path| path.exists())
        .collect()
}

/// Recursive size of `path` in bytes (best-effort: unreadable entries count 0).
pub fn dir_size_bytes(path: &Path) -> u64 {
    let mut total = 0u64;
    let mut stack = vec![path.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = std::fs::read_dir(&dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let entry_path = entry.path();
            if let Ok(meta) = entry.metadata() {
                if meta.is_dir() {
                    stack.push(entry_path);
                } else {
                    total = total.saturating_add(meta.len());
                }
            }
        }
    }
    total
}

/// True when bundling `flatpak_data_dir` deserves a size warning first.
pub fn should_warn_flatpak_bundle(flatpak_data_dir: &Path) -> bool {
    dir_size_bytes(flatpak_data_dir) >= FLATPAK_DATA_WARN_BYTES
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SaveCloudConfig {
    pub repo: String,
    pub remote: String,
    pub on_battery: bool,
    /// Path to a file holding the restic repository password. Passed as
    /// `restic --password-file`, mirroring `BackupConfig`. Empty means the
    /// repo is unencrypted or the password comes from the environment.
    #[serde(default)]
    pub password_file: String,
}

impl Default for SaveCloudConfig {
    fn default() -> Self {
        Self {
            repo: DEFAULT_REPO.into(),
            remote: String::new(),
            on_battery: false,
            password_file: String::new(),
        }
    }
}

pub fn config_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path {
        return path.as_ref().to_path_buf();
    }
    if let Some(config) = std::env::var_os("XDG_CONFIG_HOME") {
        return PathBuf::from(config).join("kyth/save-cloud.toml");
    }
    PathBuf::from(std::env::var_os("HOME").unwrap_or_else(|| ".".into()))
        .join(".config/kyth/save-cloud.toml")
}

pub fn load(path: impl AsRef<Path>) -> SaveCloudConfig {
    let Ok(raw) = std::fs::read_to_string(path) else {
        return SaveCloudConfig::default();
    };
    let Ok(value) = raw.parse::<toml::Value>() else {
        return SaveCloudConfig::default();
    };
    let Some(table) = value.as_table() else {
        return SaveCloudConfig::default();
    };
    SaveCloudConfig {
        repo: table
            .get("repo")
            .and_then(toml::Value::as_str)
            .unwrap_or(DEFAULT_REPO)
            .into(),
        remote: table
            .get("remote")
            .and_then(toml::Value::as_str)
            .unwrap_or("")
            .into(),
        on_battery: table
            .get("on_battery")
            .and_then(toml::Value::as_bool)
            .unwrap_or(false),
        password_file: table
            .get("password_file")
            .and_then(toml::Value::as_str)
            .unwrap_or("")
            .into(),
    }
}

pub fn save(path: impl AsRef<Path>, config: &SaveCloudConfig) -> std::io::Result<()> {
    let text = format!(
        "# Kyth save cloud — restic local + rclone remote, offline\nrepo = {:?}\nremote = {:?}\non_battery = {}\npassword_file = {:?}\n",
        config.repo, config.remote, config.on_battery, config.password_file,
    );
    crate::atomic_io::atomic_write_text(path, &text, Some(0o600))
}

/// Shared `--repo` / `--password-file` prefix for every restic invocation.
/// The password travels via file (or not at all), never via argv.
pub fn restic_prefix(config: &SaveCloudConfig) -> Vec<String> {
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

/// Fail closed when `repo` points at external media that is not mounted.
///
/// Writing a repo into an unmounted `/run/media/…` or `/mnt/…` stub
/// directory fills the root filesystem and strands the backup where no
/// offload will ever find it. Same-disk repos always pass (there is no
/// mount to be missing); external-prefixed repos must sit under a live
/// mount from `/proc/mounts`. Pure over explicit mounts text so it is
/// unit-testable.
pub fn repo_mount_ready(repo: &str, proc_mounts_text: &str) -> bool {
    const EXTERNAL_PREFIXES: [&str; 2] = ["/run/media/", "/mnt/"];
    if !EXTERNAL_PREFIXES
        .iter()
        .any(|prefix| repo.starts_with(prefix))
    {
        return true;
    }
    let repo = repo.trim_end_matches('/');
    for line in proc_mounts_text.lines() {
        let target = line.split_whitespace().nth(1).unwrap_or_default();
        let target = target.trim_end_matches('/');
        if !target.is_empty() && (repo == target || repo.starts_with(&format!("{target}/"))) {
            return true;
        }
    }
    false
}

/// Compat `drive_c` directories under every Steam compatdata prefix, mirroring
/// the `compatdata/*/pfx/drive_c` glob. Covers the native install plus the
/// Flatpak Steam layouts (`~/.var/app/com.valvesoftware.Steam/...`, both the
/// `data/Steam` and `.local/share/Steam` variants). Only existing paths are
/// returned, sorted and de-duplicated.
pub fn compat_drive_cs(home: &Path) -> Vec<PathBuf> {
    let mut found = Vec::new();
    for rel in [
        ".local/share/Steam/steamapps/compatdata",
        ".var/app/com.valvesoftware.Steam/data/Steam/steamapps/compatdata",
        ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/compatdata",
    ] {
        let Ok(prefixes) = std::fs::read_dir(home.join(rel)) else {
            continue;
        };
        for prefix in prefixes.flatten() {
            let candidate = prefix.path().join("pfx/drive_c");
            if candidate.exists() {
                found.push(candidate);
            }
        }
    }
    found.sort();
    found.dedup();
    found
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn finds_only_existing_compat_drive_c_paths() {
        let home = tempdir().unwrap();
        let compatdata = home.path().join(".local/share/Steam/steamapps/compatdata");
        fs::create_dir_all(compatdata.join("123/pfx/drive_c")).unwrap();
        fs::create_dir_all(compatdata.join("456/pfx")).unwrap();
        fs::create_dir_all(compatdata.join("789")).unwrap();
        assert_eq!(
            compat_drive_cs(home.path()),
            vec![compatdata.join("123/pfx/drive_c")]
        );
        assert!(compat_drive_cs(&home.path().join("missing-home")).is_empty());
    }

    #[test]
    fn finds_flatpak_steam_compatdata_and_dedupes() {
        let home = tempdir().unwrap();
        let flatpak = home
            .path()
            .join(".var/app/com.valvesoftware.Steam/data/Steam/steamapps/compatdata");
        fs::create_dir_all(flatpak.join("321/pfx/drive_c")).unwrap();
        let legacy = home
            .path()
            .join(".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/compatdata");
        fs::create_dir_all(legacy.join("654/pfx/drive_c")).unwrap();
        let found = compat_drive_cs(home.path());
        assert!(found.contains(&flatpak.join("321/pfx/drive_c")));
        assert!(found.contains(&legacy.join("654/pfx/drive_c")));
        assert_eq!(
            found.len(),
            found.iter().collect::<std::collections::HashSet<_>>().len()
        );
    }

    #[test]
    fn default_includes_cover_compat_and_kyth_state() {
        assert!(DEFAULT_RESTIC_INCLUDES
            .iter()
            .any(|rel| rel.contains("compatdata")));
        assert!(DEFAULT_RESTIC_INCLUDES.contains(&".config/kyth"));
        let home = tempdir().unwrap();
        fs::create_dir_all(home.path().join(".config/kyth")).unwrap();
        let includes = default_restic_includes(home.path());
        assert_eq!(includes, vec![home.path().join(".config/kyth")]);
    }

    #[test]
    fn flatpak_bundle_warns_only_above_threshold() {
        let small = tempdir().unwrap();
        std::fs::write(small.path().join("file.bin"), [0u8; 16]).unwrap();
        assert!(!should_warn_flatpak_bundle(small.path()));
        assert!(dir_size_bytes(&small.path().join("missing")) == 0);
        // Threshold sanity: 10 GiB, not bytes — a real shader cache trips it.
        assert_eq!(FLATPAK_DATA_WARN_BYTES, 10 * 1024 * 1024 * 1024);
    }

    #[test]
    fn restic_prefix_carries_password_file_and_mount_preflight() {
        let config = SaveCloudConfig {
            repo: "/run/media/alice/BACKUP/saves".into(),
            password_file: "/etc/kyth/saves-pass".into(),
            ..SaveCloudConfig::default()
        };
        let argv = restic_prefix(&config);
        assert_eq!(
            argv,
            vec![
                "restic",
                "--repo",
                "/run/media/alice/BACKUP/saves",
                "--password-file",
                "/etc/kyth/saves-pass",
            ]
        );
        // Legacy configs without the key keep parsing; no password flag then.
        assert!(!restic_prefix(&SaveCloudConfig::default())
            .iter()
            .any(|arg| arg == "--password-file"));
        let mounts = "/dev/sdb1 /run/media/alice/BACKUP exfat rw 0 0\n";
        assert!(repo_mount_ready("/run/media/alice/BACKUP/saves", mounts));
        assert!(!repo_mount_ready("/run/media/alice/BACKUP/saves", ""));
        assert!(!repo_mount_ready("/mnt/nas/saves", mounts));
        // Same-disk default never trips the external gate.
        assert!(repo_mount_ready(DEFAULT_REPO, ""));
    }

    #[test]
    fn defaults_when_config_is_missing() {
        let directory = tempdir().unwrap();
        assert_eq!(
            load(directory.path().join("missing.toml")),
            SaveCloudConfig::default()
        );
    }

    #[test]
    fn round_trips_quoted_save_cloud_values_atomically() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("save-cloud.toml");
        let config = SaveCloudConfig {
            repo: "/mnt/My Saves".into(),
            remote: "nas:games".into(),
            on_battery: true,
            password_file: "/etc/kyth/saves-pass".into(),
        };
        save(&path, &config).unwrap();
        assert_eq!(load(&path), config);
        assert_eq!(
            std::fs::metadata(path).unwrap().permissions().mode() & 0o077,
            0
        );
    }

    #[cfg(unix)]
    use std::os::unix::fs::PermissionsExt;
}
