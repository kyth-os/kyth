//! Explorer parity — Dolphin double-click, preview, and drives-on-desktop
//! preference. Ports `kyth_shared.explorer_preset` in full, including
//! `apply_explorer`'s `kwriteconfig5` application step (see that function's
//! doc comment for the fixed argv and the quirks it deliberately preserves).

use std::path::{Path, PathBuf};
use std::time::Duration;

use crate::system::plasma_drift::kwriteconfig_candidates;
use crate::system::process::{find_executable, run_bounded_success};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExplorerConfig {
    pub click: String,
    pub preview: bool,
    pub preview_pane: bool,
    pub drives_on_desktop: bool,
}

impl Default for ExplorerConfig {
    fn default() -> Self {
        Self {
            click: "double".into(),
            preview: true,
            preview_pane: true,
            drives_on_desktop: true,
        }
    }
}

pub fn explorer_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path {
        return path.as_ref().to_path_buf();
    }
    if let Some(config) = std::env::var_os("XDG_CONFIG_HOME") {
        return PathBuf::from(config).join("kyth/explorer.toml");
    }
    PathBuf::from(std::env::var_os("HOME").unwrap_or_else(|| ".".into()))
        .join(".config/kyth/explorer.toml")
}

pub fn load_explorer(path: impl AsRef<Path>) -> ExplorerConfig {
    let Ok(raw) = std::fs::read_to_string(path) else {
        return ExplorerConfig::default();
    };
    let Ok(value) = raw.parse::<toml::Value>() else {
        return ExplorerConfig::default();
    };
    let click = match value.get("click").and_then(toml::Value::as_str) {
        Some("single") => "single",
        _ => "double",
    };
    let flag = |key: &str| {
        value
            .get(key)
            .and_then(toml::Value::as_bool)
            .unwrap_or(true)
    };
    ExplorerConfig {
        click: click.into(),
        preview: flag("preview"),
        preview_pane: flag("preview_pane"),
        drives_on_desktop: flag("drives_on_desktop"),
    }
}

pub fn save_explorer(path: impl AsRef<Path>, config: &ExplorerConfig) -> std::io::Result<()> {
    let click = if config.click == "single" {
        "single"
    } else {
        "double"
    };
    let content = format!(
        "# Kyth Explorer parity — Windows double-click + preview + drives\nclick = \"{click}\"\npreview = {}\npreview_pane = {}\ndrives_on_desktop = {}\n",
        config.preview, config.preview_pane, config.drives_on_desktop,
    );
    crate::atomic_io::atomic_write_text(path, &content, None)
}

/// Project the click preference to a `kwriteconfig` argv.
pub fn single_click_argv(binary: &str, config: &ExplorerConfig) -> Vec<String> {
    let single = if config.click == "single" {
        "true"
    } else {
        "false"
    };
    [
        binary,
        "--file",
        "kdeglobals",
        "--group",
        "KDE",
        "--key",
        "SingleClick",
        single,
    ]
    .map(String::from)
    .to_vec()
}

/// Project `config`'s `ShowPreview` write to a `kwriteconfig` argv.
pub fn show_preview_argv(binary: &str, config: &ExplorerConfig) -> Vec<String> {
    let preview = if config.preview { "true" } else { "false" };
    [
        binary,
        "--file",
        "dolphinrc",
        "--group",
        "General",
        "--key",
        "ShowPreview",
        preview,
    ]
    .map(String::from)
    .to_vec()
}

fn apply_with_candidates(
    binaries: &[String],
    mut make_argv: impl FnMut(&str) -> Vec<String>,
    mut run: impl FnMut(&[String]) -> bool,
) -> bool {
    for binary in binaries {
        let argv = make_argv(binary);
        if run(&argv) {
            return true;
        }
    }
    false
}

fn apply_explorer_settings(
    config: &ExplorerConfig,
    binaries: &[String],
    run: &mut impl FnMut(&[String]) -> bool,
) -> Vec<String> {
    let mut applied = Vec::new();
    if apply_with_candidates(
        binaries,
        |binary| single_click_argv(binary, config),
        |argv| run(argv),
    ) {
        let single = if config.click == "single" {
            "true"
        } else {
            "false"
        };
        applied.push(format!("SingleClick={single}"));
    }
    if apply_with_candidates(
        binaries,
        |binary| show_preview_argv(binary, config),
        |argv| run(argv),
    ) {
        applied.push(format!("ShowPreview={}", config.preview));
    }
    applied
}

pub fn apply_explorer(config: &ExplorerConfig) -> Vec<String> {
    let binaries = kwriteconfig_candidates()
        .iter()
        .filter_map(|name| find_executable(name))
        .map(|path| path.to_string_lossy().into_owned())
        .collect::<Vec<_>>();
    let mut run = |argv: &[String]| run_bounded_success(argv, Duration::from_secs(5));
    let applied = apply_explorer_settings(config, &binaries, &mut run);

    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let _ = crate::atomic_io::atomic_write_text(
        "/run/kyth-explorer-ttl",
        &(now + 30).to_string(),
        None,
    );

    applied
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn defaults_when_missing_or_malformed() {
        let directory = tempdir().unwrap();
        assert_eq!(
            load_explorer(directory.path().join("missing.toml")),
            ExplorerConfig::default()
        );
        let malformed = directory.path().join("bad.toml");
        std::fs::write(&malformed, "not valid toml {{{").unwrap();
        assert_eq!(load_explorer(&malformed), ExplorerConfig::default());
    }

    #[test]
    fn round_trips_and_rejects_invalid_click() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("explorer.toml");
        let config = ExplorerConfig {
            click: "single".into(),
            preview: false,
            preview_pane: false,
            drives_on_desktop: false,
        };
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
        assert_eq!(
            explorer_path(Some("/tmp/x.toml")),
            PathBuf::from("/tmp/x.toml")
        );
    }

    #[test]
    fn single_click_argv_reflects_click_mode() {
        let single = ExplorerConfig {
            click: "single".into(),
            ..ExplorerConfig::default()
        };
        assert_eq!(
            single_click_argv("kwriteconfig6", &single),
            vec![
                "kwriteconfig6",
                "--file",
                "kdeglobals",
                "--group",
                "KDE",
                "--key",
                "SingleClick",
                "true"
            ],
        );
        let double = ExplorerConfig {
            click: "double".into(),
            ..ExplorerConfig::default()
        };
        assert_eq!(
            single_click_argv("kwriteconfig6", &double).last().unwrap(),
            "false"
        );
    }

    #[test]
    fn show_preview_argv_reflects_preview_flag() {
        let off = ExplorerConfig {
            preview: false,
            ..ExplorerConfig::default()
        };
        assert_eq!(
            show_preview_argv("kwriteconfig6", &off),
            vec![
                "kwriteconfig6",
                "--file",
                "dolphinrc",
                "--group",
                "General",
                "--key",
                "ShowPreview",
                "false"
            ],
        );
    }

    #[test]
    fn apply_explorer_uses_fallback_and_reports_both_successful_settings() {
        let config = ExplorerConfig {
            click: "single".into(),
            preview: false,
            ..ExplorerConfig::default()
        };
        let binaries = vec!["kwriteconfig6".into(), "kwriteconfig5".into()];
        let mut calls = Vec::new();
        let mut run = |argv: &[String]| {
            calls.push(argv.to_vec());
            argv[0] == "kwriteconfig5"
        };
        let applied = apply_explorer_settings(&config, &binaries, &mut run);
        assert_eq!(applied, ["SingleClick=true", "ShowPreview=false"]);
        assert_eq!(calls.len(), 4);
        assert_eq!(calls[0][0], "kwriteconfig6");
        assert_eq!(calls[1][0], "kwriteconfig5");
    }

    #[test]
    fn apply_explorer_does_not_report_nonzero_commands_as_success() {
        let mut run = |_argv: &[String]| -> bool { false };
        let applied = apply_explorer_settings(
            &ExplorerConfig::default(),
            &["kwriteconfig6".into()],
            &mut run,
        );
        assert!(applied.is_empty());
    }
}
