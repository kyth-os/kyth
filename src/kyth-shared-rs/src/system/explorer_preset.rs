//! Explorer parity — Dolphin double-click, preview, and drives-on-desktop
//! preference, offline. Ports `kyth_shared.explorer_preset`'s config model;
//! the `kwriteconfig5`/Dolphin application step remains Python-owned.

use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExplorerConfig {
    pub click: String,
    pub preview: bool,
    pub preview_pane: bool,
    pub drives_on_desktop: bool,
}

impl Default for ExplorerConfig {
    fn default() -> Self {
        Self { click: "double".into(), preview: true, preview_pane: true, drives_on_desktop: true }
    }
}

pub fn explorer_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path {
        return path.as_ref().to_path_buf();
    }
    if let Some(config) = std::env::var_os("XDG_CONFIG_HOME") {
        return PathBuf::from(config).join("kyth/explorer.toml");
    }
    PathBuf::from(std::env::var_os("HOME").unwrap_or_else(|| ".".into())).join(".config/kyth/explorer.toml")
}

pub fn load_explorer(path: impl AsRef<Path>) -> ExplorerConfig {
    let Ok(raw) = std::fs::read_to_string(path) else { return ExplorerConfig::default(); };
    let Ok(value) = raw.parse::<toml::Value>() else { return ExplorerConfig::default(); };
    let click = match value.get("click").and_then(toml::Value::as_str) {
        Some("single") => "single",
        _ => "double",
    };
    let flag = |key: &str| value.get(key).and_then(toml::Value::as_bool).unwrap_or(true);
    ExplorerConfig {
        click: click.into(),
        preview: flag("preview"),
        preview_pane: flag("preview_pane"),
        drives_on_desktop: flag("drives_on_desktop"),
    }
}

pub fn save_explorer(path: impl AsRef<Path>, config: &ExplorerConfig) -> std::io::Result<()> {
    let click = if config.click == "single" { "single" } else { "double" };
    let content = format!(
        "# Kyth Explorer parity — Windows double-click + preview + drives\nclick = \"{click}\"\npreview = {}\npreview_pane = {}\ndrives_on_desktop = {}\n",
        config.preview, config.preview_pane, config.drives_on_desktop,
    );
    crate::atomic_io::atomic_write_text(path, &content, None)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn defaults_when_missing_or_malformed() {
        let directory = tempdir().unwrap();
        assert_eq!(load_explorer(directory.path().join("missing.toml")), ExplorerConfig::default());
        let malformed = directory.path().join("bad.toml");
        std::fs::write(&malformed, "not valid toml {{{").unwrap();
        assert_eq!(load_explorer(&malformed), ExplorerConfig::default());
    }

    #[test]
    fn round_trips_and_rejects_invalid_click() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("explorer.toml");
        let config = ExplorerConfig { click: "single".into(), preview: false, preview_pane: false, drives_on_desktop: false };
        save_explorer(&path, &config).unwrap();
        assert_eq!(load_explorer(&path), config);

        std::fs::write(&path, "click = \"sideways\"\n").unwrap();
        assert_eq!(load_explorer(&path).click, "double");
    }

    #[test]
    fn explorer_path_honors_an_explicit_override() {
        // Env-var fallback branches are exercised by inspection against the
        // Python original rather than by mutating process-global XDG_*
        // state here — see MIGRATION.md on keeping tests parallel-safe.
        assert_eq!(explorer_path(Some("/tmp/x.toml")), PathBuf::from("/tmp/x.toml"));
    }
}
