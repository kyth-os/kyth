//! Pure policy/config helpers from `kyth_shared.safe_upgrade`.
//!
//! The privileged upgrade workflow remains Python-owned. This module only
//! reads the rollout setting and projects the fixed argv used by the
//! `/boot` remount/finalize boundary, so callers can review and test that
//! policy without starting an upgrade or mounting anything.

use std::path::Path;

pub const DEFAULT_CONFIG_PATH: &str = "/etc/kyth/auto-update.toml";
pub const DEFAULT_ROLLOUT_RING: &str = "follow-image";

/// Decode the rollout setting from captured TOML without performing I/O.
pub fn rollout_ring_from_toml(raw: &str) -> String {
    let Ok(value) = raw.parse::<toml::Value>() else {
        return DEFAULT_ROLLOUT_RING.into();
    };
    let Some(section) = value.get("auto_update").and_then(toml::Value::as_table) else {
        return DEFAULT_ROLLOUT_RING.into();
    };
    match section.get("rollout_ring") {
        Some(toml::Value::String(value)) => value.clone(),
        Some(toml::Value::Boolean(value)) => if *value { "True" } else { "False" }.into(),
        Some(toml::Value::Integer(value)) => value.to_string(),
        Some(toml::Value::Float(value)) => value.to_string(),
        Some(toml::Value::Datetime(value)) => value.to_string(),
        Some(_) | None => DEFAULT_ROLLOUT_RING.into(),
    }
}

/// Read the configured rollout ring with the same fail-safe default as the
/// Python helper. Missing, unreadable, and malformed files follow-image.
pub fn load_rollout_ring(path: impl AsRef<Path>) -> String {
    std::fs::read_to_string(path)
        .map(|raw| rollout_ring_from_toml(&raw))
        .unwrap_or_else(|_| DEFAULT_ROLLOUT_RING.into())
}

/// The fixed remount attempts safe-upgrade makes, in order of preference.
/// Returning argv keeps execution and privilege decisions with the caller.
pub fn boot_remount_commands() -> [Vec<String>; 2] {
    [
        ["mount", "-o", "remount,bind,rw", "/boot"].into_iter().map(String::from).collect(),
        ["mount", "-o", "remount,rw", "/boot"].into_iter().map(String::from).collect(),
    ]
}

pub fn bind_sysroot_boot_command() -> Vec<String> {
    ["mount", "--bind", "/boot", "/sysroot/boot"].into_iter().map(String::from).collect()
}

pub fn finalize_staged_command() -> Vec<String> {
    ["ostree", "admin", "finalize-staged"].into_iter().map(String::from).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn parses_rollout_ring_and_safe_defaults() {
        assert_eq!(rollout_ring_from_toml("[auto_update]\nrollout_ring = \"testing\"\n"), "testing");
        assert_eq!(rollout_ring_from_toml("[auto_update]\nrollout_ring = true\n"), "True");
        assert_eq!(rollout_ring_from_toml("not toml"), DEFAULT_ROLLOUT_RING);
        assert_eq!(rollout_ring_from_toml("[other]\nvalue = 1\n"), DEFAULT_ROLLOUT_RING);
    }

    #[test]
    fn loads_rollout_ring_from_an_explicit_path() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("auto-update.toml");
        fs::write(&path, "[auto_update]\nrollout_ring = \"canary\"\n").unwrap();
        assert_eq!(load_rollout_ring(&path), "canary");
        assert_eq!(load_rollout_ring(directory.path().join("missing.toml")), DEFAULT_ROLLOUT_RING);
    }

    #[test]
    fn projects_only_the_fixed_upgrade_boundary_commands() {
        assert_eq!(boot_remount_commands()[0], vec!["mount", "-o", "remount,bind,rw", "/boot"]);
        assert_eq!(boot_remount_commands()[1], vec!["mount", "-o", "remount,rw", "/boot"]);
        assert_eq!(bind_sysroot_boot_command(), vec!["mount", "--bind", "/boot", "/sysroot/boot"]);
        assert_eq!(finalize_staged_command(), vec!["ostree", "admin", "finalize-staged"]);
    }
}
