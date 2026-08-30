//! Offline work-cache configuration model.
//!
//! The systemd/tmpfiles generator remains outside this crate because it
//! writes privileged unit files and mount commands. Native callers can still
//! read and edit the user-facing configuration without crossing that boundary.

use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WorkCacheConfig {
    pub enabled: bool,
    pub size: String,
}

impl Default for WorkCacheConfig {
    fn default() -> Self { Self { enabled: false, size: "1G".into() } }
}

fn normalize_size(value: Option<&str>) -> String {
    match value.unwrap_or("1G") { "2G" => "2G".into(), "4G" => "4G".into(), _ => "1G".into() }
}

pub fn config_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path { return path.as_ref().to_path_buf(); }
    if std::env::var("KYTH_TEST_MODE").ok().as_deref() == Some("1") {
        if let Some(config) = std::env::var_os("XDG_CONFIG_HOME") { return PathBuf::from(config).join("kyth/work-cache.toml"); }
    }
    PathBuf::from("/etc/kyth/work-cache.toml")
}

pub fn load(path: impl AsRef<Path>) -> WorkCacheConfig {
    let Ok(raw) = std::fs::read_to_string(path) else { return WorkCacheConfig::default(); };
    let Ok(value) = raw.parse::<toml::Value>() else { return WorkCacheConfig::default(); };
    WorkCacheConfig {
        enabled: value.get("enabled").and_then(toml::Value::as_bool).unwrap_or(false),
        size: normalize_size(value.get("size").and_then(toml::Value::as_str)),
    }
}

pub fn save(path: impl AsRef<Path>, config: &WorkCacheConfig) -> std::io::Result<()> {
    let text = format!("# Kyth work cache — offline\nenabled = {}\nsize = {:?}\n", config.enabled, normalize_size(Some(&config.size)));
    crate::atomic_io::atomic_write_text(path, &text, Some(0o600))
}

pub fn status(service: impl AsRef<Path>) -> &'static str { if service.as_ref().is_file() { "enabled" } else { "off" } }

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn defaults_and_clamps_cache_size() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("work-cache.toml");
        assert_eq!(load(&path), WorkCacheConfig::default());
        std::fs::write(&path, "enabled = true\nsize = \"99G\"\n").unwrap();
        assert_eq!(load(&path), WorkCacheConfig { enabled: true, size: "1G".into() });
    }

    #[test]
    fn saves_and_reports_service_presence() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("work-cache.toml");
        save(&path, &WorkCacheConfig { enabled: true, size: "4G".into() }).unwrap();
        assert_eq!(load(&path).size, "4G");
        let service = directory.path().join("service");
        assert_eq!(status(&service), "off");
        std::fs::write(&service, "unit").unwrap();
        assert_eq!(status(&service), "enabled");
    }
}
