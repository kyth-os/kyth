//! Read-only Plasma launcher discovery and command projections.
//!
//! These helpers cover the non-mutating half of `desktop.plasma`: callers
//! supply filesystem roots or execute the returned argv themselves.  Rust
//! never invokes `kwriteconfig`, `qdbus`, or a Plasma script here.

use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LauncherChoice {
    Single(String),
    Alternatives(Vec<String>),
}

pub const LAYOUT_VERSION: &str = "kyth-comfort-v4";

pub fn desktop_name(value: &str) -> &str {
    value.strip_prefix("applications:").unwrap_or(value)
}

pub fn desktop_exists(value: &str, roots: &[impl AsRef<Path>]) -> bool {
    let name = desktop_name(value);
    roots.iter().any(|root| root.as_ref().join(name).is_file())
}

pub fn filter_available_launchers(choices: &[LauncherChoice], roots: &[impl AsRef<Path>]) -> Vec<String> {
    choices.iter().filter_map(|choice| {
        let candidates = match choice {
            LauncherChoice::Single(value) => std::slice::from_ref(value),
            LauncherChoice::Alternatives(values) => values.as_slice(),
        };
        candidates.iter().find(|candidate| desktop_exists(candidate, roots)).cloned()
    }).collect()
}

pub fn default_launchers() -> Vec<LauncherChoice> {
    vec![
        LauncherChoice::Single("applications:kyth-welcome.desktop".into()),
        LauncherChoice::Single("applications:kyth-app-store.desktop".into()),
        LauncherChoice::Alternatives(vec!["applications:com.valvesoftware.Steam.desktop".into(), "applications:steam.desktop".into()]),
        LauncherChoice::Alternatives(vec!["applications:com.brave.Browser.desktop".into(), "applications:chromium-browser.desktop".into()]),
        LauncherChoice::Single("applications:org.kde.dolphin.desktop".into()),
        LauncherChoice::Single("applications:org.kde.konsole.desktop".into()),
    ]
}

pub fn qdbus_candidates() -> [&'static str; 3] {
    ["qdbus6", "qdbus-qt6", "qdbus"]
}

pub fn kreadconfig_argv(binary: &str, file: &str, group: &str, key: &str) -> Vec<String> {
    vec![binary.into(), "--file".into(), file.into(), "--group".into(), group.into(), "--key".into(), key.into()]
}

pub fn kwriteconfig_argv(binary: &str, file: &str, groups: &[&str], key: &str, value: &str, value_type: Option<&str>) -> Vec<String> {
    let mut argv = vec![binary.into(), "--file".into(), file.into()];
    for group in groups { argv.extend(["--group".into(), (*group).into()]); }
    argv.extend(["--key".into(), key.into()]);
    if let Some(value_type) = value_type { argv.extend(["--type".into(), value_type.into()]); }
    argv.push(value.into());
    argv
}

pub fn evaluate_plasma_argv(qdbus: &str, script: &str) -> Vec<String> {
    vec![qdbus.into(), "org.kde.plasmashell".into(), "/PlasmaShell".into(), "org.kde.PlasmaShell.evaluateScript".into(), script.into()]
}

/// Common roots used by the Python launcher discovery helper.
pub fn default_application_roots(home: impl AsRef<Path>) -> Vec<PathBuf> {
    let home = home.as_ref();
    vec![
        PathBuf::from("/usr/share/applications"),
        PathBuf::from("/var/lib/flatpak/exports/share/applications"),
        home.join(".local/share/applications"),
        home.join(".local/share/flatpak/exports/share/applications"),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn filters_first_available_launcher_alternative() {
        let directory = tempdir().unwrap();
        fs::write(directory.path().join("steam.desktop"), "[Desktop Entry]\n").unwrap();
        let choices = vec![LauncherChoice::Alternatives(vec!["applications:missing.desktop".into(), "applications:steam.desktop".into()])];
        assert_eq!(filter_available_launchers(&choices, &[directory.path()]), vec!["applications:steam.desktop"]);
    }

    #[test]
    fn projects_nested_kwriteconfig_and_qdbus_argv() {
        assert_eq!(kreadconfig_argv("kreadconfig6", "kwinrc", "Compositing", "AllowTearing"), vec!["kreadconfig6", "--file", "kwinrc", "--group", "Compositing", "--key", "AllowTearing"]);
        assert_eq!(kwriteconfig_argv("kwriteconfig6", "kwinrc", &["Containments", "1", "General"], "foo", "bar", Some("string")), vec!["kwriteconfig6", "--file", "kwinrc", "--group", "Containments", "--group", "1", "--group", "General", "--key", "foo", "--type", "string", "bar"]);
        assert_eq!(evaluate_plasma_argv("qdbus6", "print('ok')")[3], "org.kde.PlasmaShell.evaluateScript");
    }

    #[test]
    fn default_launcher_shape_remains_stable() {
        assert_eq!(default_launchers().len(), 6);
        assert_eq!(qdbus_candidates(), ["qdbus6", "qdbus-qt6", "qdbus"]);
        assert_eq!(desktop_name("applications:foo.desktop"), "foo.desktop");
        assert_eq!(LAYOUT_VERSION, "kyth-comfort-v4");
    }
}
