//! Offline backup configuration model.

use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BackupConfig {
    pub repo: String,
    pub btrfs_send: bool,
    pub on_battery: bool,
    pub remote: String,
}

impl Default for BackupConfig {
    fn default() -> Self { Self { repo: "/var/cache/kyth/backup".into(), btrfs_send: false, on_battery: false, remote: String::new() } }
}

pub fn config_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path { return path.as_ref().to_path_buf(); }
    if std::env::var("KYTH_TEST_MODE").ok().as_deref() == Some("1") {
        if let Some(config) = std::env::var_os("XDG_CONFIG_HOME") { return PathBuf::from(config).join("kyth/backup.toml"); }
    }
    PathBuf::from("/etc/kyth/backup.toml")
}

pub fn load(path: impl AsRef<Path>) -> BackupConfig {
    let Ok(raw) = std::fs::read_to_string(path) else { return BackupConfig::default(); };
    let Ok(value) = raw.parse::<toml::Value>() else { return BackupConfig::default(); };
    let table = value.as_table();
    BackupConfig {
        repo: table.and_then(|table| table.get("repo")).and_then(toml::Value::as_str).unwrap_or("/var/cache/kyth/backup").to_string(),
        btrfs_send: table.and_then(|table| table.get("btrfs_send")).and_then(toml::Value::as_bool).unwrap_or(false),
        on_battery: table.and_then(|table| table.get("on_battery")).and_then(toml::Value::as_bool).unwrap_or(false),
        remote: table.and_then(|table| table.get("remote")).and_then(toml::Value::as_str).unwrap_or("").to_string(),
    }
}

pub fn save(path: impl AsRef<Path>, config: &BackupConfig) -> std::io::Result<()> {
    let text = format!("# Kyth backup full /home\nrepo = {:?}\nbtrfs_send = {}\non_battery = {}\nremote = {:?}\n", config.repo, config.btrfs_send, config.on_battery, config.remote);
    crate::atomic_io::atomic_write_text(path, &text, Some(0o600))
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn round_trips_backup_config() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("backup.toml");
        let config = BackupConfig { repo: "/mnt/backup".into(), btrfs_send: true, on_battery: true, remote: "nas".into() };
        save(&path, &config).unwrap();
        assert_eq!(load(&path), config);
    }
}
