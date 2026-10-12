//! Boot-loader fast-path configuration.
//!
//! Reads the Kyth loader TOML config and applies the `timeout` setting to the
//! systemd-boot `/boot/loader/loader.conf`. Writes are line surgery only:
//! the `timeout` line is replaced or appended while `default`,
//! `console-mode`, and every other existing setting is preserved — the file
//! is never wholesale regenerated.

use std::fs;
use std::path::{Path, PathBuf};

const DEFAULT_CONFIG_PATH: &str = "/etc/kyth/loader.toml";
const DEFAULT_LOADER_CONF: &str = "/boot/loader/loader.conf";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LoaderConfig {
    pub fast: bool,
    pub timeout: i64,
}

impl Default for LoaderConfig {
    fn default() -> Self {
        Self {
            fast: false,
            timeout: 2,
        }
    }
}

pub fn loader_config_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path {
        return path.as_ref().to_path_buf();
    }
    if crate::system::test_mode_active() {
        if let Some(config) = std::env::var_os("XDG_CONFIG_HOME") {
            return PathBuf::from(config).join("kyth/loader.toml");
        }
    }
    PathBuf::from(DEFAULT_CONFIG_PATH)
}

pub fn load_loader(path: impl AsRef<Path>) -> LoaderConfig {
    let Ok(raw) = fs::read_to_string(path) else {
        return LoaderConfig::default();
    };
    let Ok(value) = raw.parse::<toml::Value>() else {
        return LoaderConfig::default();
    };
    let table = value.as_table();
    let fast = table
        .and_then(|table| table.get("fast"))
        .and_then(toml::Value::as_bool)
        .unwrap_or(false);
    let default_timeout = if fast { 0 } else { 2 };
    let timeout = table
        .and_then(|table| table.get("timeout"))
        .and_then(toml::Value::as_integer)
        .unwrap_or(default_timeout)
        .clamp(0, 10);
    LoaderConfig { fast, timeout }
}

pub fn load_loader_default() -> LoaderConfig {
    load_loader(loader_config_path(None::<PathBuf>))
}

pub fn save_loader(path: impl AsRef<Path>, config: &LoaderConfig) -> std::io::Result<()> {
    let timeout = config.timeout.clamp(0, 10);
    crate::atomic_io::atomic_write_text(
        path,
        &format!(
            "# Kyth loader — offline\nfast = {}\ntimeout = {}\n",
            config.fast, timeout
        ),
        Some(0o600),
    )
}

pub fn loader_status(conf: impl AsRef<Path>) -> &'static str {
    let Ok(raw) = fs::read_to_string(conf) else {
        return "balanced";
    };
    if raw.contains("timeout 0") || raw.contains("Kyth") {
        "fast"
    } else {
        "balanced"
    }
}

pub fn loader_status_default() -> &'static str {
    loader_status(DEFAULT_LOADER_CONF)
}

pub fn generate_loader_conf(
    config: &LoaderConfig,
    destination: impl AsRef<Path>,
) -> std::io::Result<Option<PathBuf>> {
    let destination = destination.as_ref();
    let timeout = config.timeout.clamp(0, 10);
    if !config.fast {
        // Not fast-path: only touch a file we previously generated (marked
        // "Kyth"), reset its timeout to the default, drop our marker so we
        // stop managing it — but preserve every other line.
        if destination.is_file()
            && fs::read_to_string(destination)
                .ok()
                .is_some_and(|text| text.contains("Kyth"))
        {
            set_timeout_line(destination, 2, false)?;
        }
        return Ok(None);
    }
    set_timeout_line(destination, timeout, true)?;
    Ok(Some(destination.to_path_buf()))
}

/// Replace (or append) only the `timeout` line in loader.conf, preserving
/// every other line (`default`, `console-mode`, ...). When `manage` is true
/// our marker comment is ensured; when false it is removed so future runs
/// stop touching the file. Writes atomically.
fn set_timeout_line(destination: &Path, timeout: i64, manage: bool) -> std::io::Result<()> {
    let lines: Vec<String> = fs::read_to_string(destination)
        .map(|text| text.lines().map(str::to_string).collect())
        .unwrap_or_default();
    let mut kept = Vec::with_capacity(lines.len() + 1);
    let mut found = false;
    for line in lines {
        let trimmed = line.trim_start();
        if trimmed.len() > "timeout".len()
            && trimmed.starts_with("timeout")
            && trimmed["timeout".len()..].starts_with([' ', '\t'])
        {
            kept.push(format!("timeout {timeout}"));
            found = true;
        } else if !manage && trimmed.starts_with("# Kyth loader") {
            // Un-managing: drop our marker comment, keep everything else.
            continue;
        } else {
            kept.push(line);
        }
    }
    if !found {
        kept.push(format!("timeout {timeout}"));
    }
    if manage && !kept.iter().any(|line| line.contains("Kyth")) {
        kept.insert(
            0,
            "# Kyth loader fast-path — generated, greenboot-aware".to_string(),
        );
    }
    let mut text = kept.join("\n");
    text.push('\n');
    crate::atomic_io::atomic_write_text(destination, &text, Some(0o644))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn loads_defaults_and_clamps_timeout() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("loader.toml");
        fs::write(&path, "fast = true\ntimeout = 99\n").unwrap();
        assert_eq!(
            load_loader(&path),
            LoaderConfig {
                fast: true,
                timeout: 10
            }
        );
        assert_eq!(
            load_loader(directory.path().join("missing.toml")),
            LoaderConfig::default()
        );
    }

    #[test]
    fn detects_effective_loader_status() {
        let directory = tempdir().unwrap();
        let fast = directory.path().join("loader.conf");
        fs::write(&fast, "# Kyth loader\ntimeout 0\n").unwrap();
        assert_eq!(loader_status(&fast), "fast");
        fs::write(&fast, "timeout 2\n").unwrap();
        assert_eq!(loader_status(&fast), "balanced");
        assert_eq!(loader_status(directory.path().join("missing")), "balanced");
    }

    #[test]
    fn generate_preserves_unrelated_lines() {
        let directory = tempdir().unwrap();
        let conf = directory.path().join("loader.conf");
        fs::write(
            &conf,
            "default kyth.conf\ntimeout 10\nconsole-mode max\n# a comment\n",
        )
        .unwrap();
        let config = LoaderConfig {
            fast: true,
            timeout: 0,
        };
        generate_loader_conf(&config, &conf).unwrap();
        let text = fs::read_to_string(&conf).unwrap();
        assert!(text.contains("default kyth.conf"), "{text}");
        assert!(text.contains("console-mode max"), "{text}");
        assert!(text.contains("# a comment"), "{text}");
        assert!(text.contains("timeout 0"), "{text}");
        assert!(!text.contains("timeout 10"), "{text}");
        assert!(text.contains("Kyth"), "{text}");
    }

    #[test]
    fn generate_appends_timeout_when_missing() {
        let directory = tempdir().unwrap();
        let conf = directory.path().join("loader.conf");
        fs::write(&conf, "default kyth.conf\n").unwrap();
        let config = LoaderConfig {
            fast: true,
            timeout: 3,
        };
        generate_loader_conf(&config, &conf).unwrap();
        let text = fs::read_to_string(&conf).unwrap();
        assert!(text.contains("default kyth.conf"), "{text}");
        assert!(text.contains("timeout 3"), "{text}");
    }

    #[test]
    fn unmanage_resets_timeout_and_drops_marker_but_keeps_other_lines() {
        let directory = tempdir().unwrap();
        let conf = directory.path().join("loader.conf");
        fs::write(
            &conf,
            "# Kyth loader fast-path — generated, greenboot-aware\ndefault kyth.conf\ntimeout 0\nconsole-mode max\n",
        )
        .unwrap();
        let config = LoaderConfig {
            fast: false,
            timeout: 2,
        };
        generate_loader_conf(&config, &conf).unwrap();
        let text = fs::read_to_string(&conf).unwrap();
        assert!(text.contains("timeout 2"), "{text}");
        assert!(!text.contains("timeout 0"), "{text}");
        assert!(text.contains("default kyth.conf"), "{text}");
        assert!(text.contains("console-mode max"), "{text}");
        assert!(!text.contains("Kyth loader fast-path"), "{text}");
    }

    #[test]
    fn unmanage_leaves_unowned_files_alone() {
        let directory = tempdir().unwrap();
        let conf = directory.path().join("loader.conf");
        fs::write(&conf, "default kyth.conf\ntimeout 5\n").unwrap();
        let config = LoaderConfig {
            fast: false,
            timeout: 2,
        };
        generate_loader_conf(&config, &conf).unwrap();
        assert_eq!(
            fs::read_to_string(&conf).unwrap(),
            "default kyth.conf\ntimeout 5\n"
        );
    }
}
