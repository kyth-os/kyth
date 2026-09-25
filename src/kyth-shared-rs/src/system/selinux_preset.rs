//! Native port of `kyth_shared.selinux_preset`.
//!
//! Loads, saves, and applies `/etc/kyth/selinux.toml`: permissive domains
//! plus persistent booleans. The Python module remains a compatible reader;
//! new callers use this. Unlike the old Python saver (which rendered the
//! permissive list with Python-repr single quotes that TOML cannot parse
//! back), this writer emits valid double-quoted TOML and round-trips.

use std::collections::BTreeMap;
use std::io;
use std::path::{Path, PathBuf};
use std::time::Duration;

pub const DEFAULT_SELINUX_PATH: &str = "/etc/kyth/selinux.toml";

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SelinuxPreset {
    pub permissive: Vec<String>,
    pub booleans: BTreeMap<String, bool>,
}

/// Resolve the preset path: explicit override wins, then the XDG test
/// location under `KYTH_TEST_MODE=1`, then the system default. Mirrors the
/// Python `selinux_path` precedence exactly.
pub fn selinux_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path {
        return path.as_ref().to_path_buf();
    }
    if std::env::var("KYTH_TEST_MODE").ok().as_deref() == Some("1") {
        if let Some(xdg) = std::env::var_os("XDG_CONFIG_HOME") {
            return PathBuf::from(xdg).join("kyth/selinux.toml");
        }
    }
    PathBuf::from(DEFAULT_SELINUX_PATH)
}

pub fn load_selinux(path: Option<impl AsRef<Path>>) -> SelinuxPreset {
    let raw = std::fs::read_to_string(selinux_path(path)).unwrap_or_default();
    let value: toml::Value = raw
        .parse()
        .unwrap_or(toml::Value::Table(Default::default()));
    let table = value.as_table().cloned().unwrap_or_default();
    let permissive = table
        .get("permissive")
        .and_then(toml::Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(toml::Value::as_str)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default();
    // Python coerces with bool(v) rather than rejecting wrong types, so a
    // truthy string enables the boolean. Match that exactly: the compat
    // reader and this port must agree on the same file.
    fn truthy(value: &toml::Value) -> bool {
        match value {
            toml::Value::Boolean(flag) => *flag,
            toml::Value::Integer(number) => *number != 0,
            toml::Value::Float(number) => *number != 0.0,
            toml::Value::String(text) => !text.is_empty(),
            toml::Value::Datetime(_) => true,
            toml::Value::Array(items) => !items.is_empty(),
            toml::Value::Table(entries) => !entries.is_empty(),
        }
    }
    let booleans = table
        .get("booleans")
        .and_then(toml::Value::as_table)
        .map(|entries| {
            entries
                .iter()
                .map(|(key, value)| (key.clone(), truthy(value)))
                .collect()
        })
        .unwrap_or_default();
    SelinuxPreset {
        permissive,
        booleans,
    }
}

fn render(cfg: &SelinuxPreset) -> String {
    let mut text = String::from("# Kyth SELinux preset, offline\n");
    text.push_str("permissive = [");
    for (index, domain) in cfg.permissive.iter().enumerate() {
        if index > 0 {
            text.push_str(", ");
        }
        text.push('"');
        text.push_str(&domain.replace('"', ""));
        text.push('"');
    }
    text.push_str("]\n[booleans]\n");
    for (key, flag) in &cfg.booleans {
        text.push_str(&format!(
            "{key} = {}\n",
            if *flag { "true" } else { "false" }
        ));
    }
    text
}

/// Atomically write the preset, creating the parent directory. Returns the
/// path written.
pub fn save_selinux(cfg: &SelinuxPreset, path: Option<impl AsRef<Path>>) -> io::Result<PathBuf> {
    let path = selinux_path(path);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    crate::atomic_io::atomic_write_text(&path, &render(cfg), None)?;
    Ok(path)
}

/// Apply the preset with best-effort per-command semantics: skip everything
/// when SELinux is unavailable or disabled, continue after individual
/// failures, and report only commands that exited successfully.
pub fn apply_selinux(cfg: &SelinuxPreset) -> Vec<String> {
    if !Path::new("/usr/sbin/selinuxenabled").exists()
        && !Path::new("/usr/bin/selinuxenabled").exists()
    {
        return Vec::new();
    }
    let enabled = crate::system::process::run_bounded(
        &["selinuxenabled".to_string()],
        Duration::from_secs(3),
    )
    .map(|output| output.status.success())
    .unwrap_or(false);
    if !enabled {
        return Vec::new();
    }
    let mut applied = Vec::new();
    for domain in &cfg.permissive {
        let succeeded = crate::system::process::run_bounded_success(
            &[
                "semanage".to_string(),
                "permissive".to_string(),
                "-a".to_string(),
                domain.clone(),
            ],
            Duration::from_secs(5),
        );
        if succeeded {
            applied.push(format!("permissive:{domain}"));
        }
    }
    for (key, flag) in &cfg.booleans {
        let succeeded = crate::system::process::run_bounded_success(
            &[
                "setsebool".to_string(),
                "-P".to_string(),
                key.clone(),
                if *flag { "on" } else { "off" }.to_string(),
            ],
            Duration::from_secs(5),
        );
        if succeeded {
            applied.push(format!("boolean:{key}={flag}"));
        }
    }
    applied
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn preset() -> SelinuxPreset {
        SelinuxPreset {
            permissive: vec!["httpd_t".into(), "dnsmasq_t".into()],
            booleans: [("httpd_can_network_connect".into(), true)].into(),
        }
    }

    #[test]
    fn save_round_trips_through_valid_toml() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("selinux.toml");
        save_selinux(&preset(), Some(&path)).unwrap();
        let raw = std::fs::read_to_string(&path).unwrap();
        // The old Python saver wrote single-quoted reprs that TOML rejects.
        assert!(!raw.contains('\''));
        let loaded = load_selinux(Some(&path));
        assert_eq!(loaded, preset());
    }

    #[test]
    fn missing_or_malformed_file_loads_defaults() {
        let directory = tempdir().unwrap();
        let missing = directory.path().join("absent.toml");
        assert_eq!(load_selinux(Some(&missing)), SelinuxPreset::default());
        let bad = directory.path().join("bad.toml");
        std::fs::write(&bad, "permissive = [unquoted\n[booleans\n").unwrap();
        assert_eq!(load_selinux(Some(&bad)), SelinuxPreset::default());
        let wrong_types = directory.path().join("types.toml");
        std::fs::write(
            &wrong_types,
            "permissive = \"nope\"\n[booleans]\nflag = \"maybe\"\nempty = \"\"\nzero = 0\n",
        )
        .unwrap();
        // Matches Python's bool(v) coercion exactly (see test_wrong_types...
        // in tests/test_kyth_selinux_preset.py).
        let loaded = load_selinux(Some(&wrong_types));
        assert!(loaded.permissive.is_empty());
        assert_eq!(
            loaded.booleans,
            [
                ("empty".to_string(), false),
                ("flag".to_string(), true),
                ("zero".to_string(), false),
            ]
            .into_iter()
            .collect()
        );
    }

    #[test]
    fn test_mode_resolves_under_xdg_config() {
        std::env::set_var("KYTH_TEST_MODE", "1");
        std::env::set_var("XDG_CONFIG_HOME", "/tmp/kyth-test-xdg");
        assert_eq!(
            selinux_path(None::<&Path>),
            PathBuf::from("/tmp/kyth-test-xdg/kyth/selinux.toml")
        );
        std::env::remove_var("KYTH_TEST_MODE");
        std::env::remove_var("XDG_CONFIG_HOME");
    }

    #[test]
    fn apply_skips_when_selinux_tooling_is_absent() {
        if Path::new("/usr/sbin/selinuxenabled").exists()
            || Path::new("/usr/bin/selinuxenabled").exists()
        {
            return;
        }
        assert!(apply_selinux(&preset()).is_empty());
    }
}
