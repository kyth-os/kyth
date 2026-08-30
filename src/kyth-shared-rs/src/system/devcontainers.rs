//! Declarative Distrobox/dev-container configuration.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DevContainer {
    pub image: String,
    pub init: bool,
}

impl Default for DevContainer {
    fn default() -> Self { Self { image: "quay.io/toolbx/ubuntu-toolbox:24.04".into(), init: false } }
}

pub fn config_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path { return path.as_ref().to_path_buf(); }
    if let Some(config) = std::env::var_os("XDG_CONFIG_HOME") { return PathBuf::from(config).join("kyth/devcontainers.toml"); }
    PathBuf::from(std::env::var_os("HOME").unwrap_or_else(|| ".".into())).join(".config/kyth/devcontainers.toml")
}

pub fn load(path: impl AsRef<Path>) -> BTreeMap<String, DevContainer> {
    let Ok(raw) = std::fs::read_to_string(path) else { return BTreeMap::new(); };
    let Ok(value) = raw.parse::<toml::Value>() else { return BTreeMap::new(); };
    value.get("containers").and_then(toml::Value::as_table).map(|containers| containers.iter().filter_map(|(name, value)| {
        let entry = value.as_table()?;
        Some((name.clone(), DevContainer {
            image: entry.get("image").and_then(toml::Value::as_str).unwrap_or("quay.io/toolbx/ubuntu-toolbox:24.04").to_string(),
            init: entry.get("init").and_then(toml::Value::as_bool).unwrap_or(false),
        }))
    }).collect()).unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn loads_container_defaults() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("devcontainers.toml");
        fs::write(&path, "[containers.kyth]\nimage = \"quay.io/kyth/dev:latest\"\ninit = true\n").unwrap();
        assert_eq!(load(&path)["kyth"], DevContainer { image: "quay.io/kyth/dev:latest".into(), init: true });
    }
}
