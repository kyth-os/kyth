//! Declarative, offline role-preset model.
//!
//! This ports the durable preset TOML contract. Installing Flatpaks,
//! creating Distroboxes, and installing editor extensions remain explicit
//! service actions and are intentionally not hidden behind this model.

use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Role { Everyday, Gaming, Dev, Creator }

impl Role {
    pub fn parse(value: Option<&str>) -> Self {
        match value.unwrap_or("everyday") {
            "gaming" => Self::Gaming,
            "dev" => Self::Dev,
            "creator" => Self::Creator,
            _ => Self::Everyday,
        }
    }
    pub fn as_str(self) -> &'static str { match self { Self::Everyday => "everyday", Self::Gaming => "gaming", Self::Dev => "dev", Self::Creator => "creator" } }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RolePreset {
    pub profile: Role,
    pub flatpaks: Vec<String>,
    pub distroboxes: Vec<String>,
    pub vscode_extensions: Vec<String>,
}

fn values(profile: Role) -> RolePreset {
    let (flatpaks, distroboxes, vscode_extensions) = match profile {
        Role::Everyday => (vec!["com.brave.Browser", "com.valvesoftware.Steam"], vec![], vec![]),
        Role::Gaming => (vec!["com.valvesoftware.Steam", "net.lutris.Lutris", "com.heroicgameslauncher.hgl", "com.github.Matoking.protontricks"], vec![], vec![]),
        Role::Dev => (vec!["com.visualstudio.code", "com.github.flathub.flatpak-external-data-checker"], vec!["kyth-ai-dev"], vec!["ms-python.python", "rust-lang.rust-analyzer"]),
        Role::Creator => (vec!["com.obsproject.Studio", "org.kde.kdenlive"], vec![], vec![]),
    };
    RolePreset { profile, flatpaks: flatpaks.into_iter().map(String::from).collect(), distroboxes: distroboxes.into_iter().map(String::from).collect(), vscode_extensions: vscode_extensions.into_iter().map(String::from).collect() }
}

impl Default for RolePreset { fn default() -> Self { values(Role::Everyday) } }

pub fn config_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path { return path.as_ref().to_path_buf(); }
    if let Some(config) = std::env::var_os("XDG_CONFIG_HOME") { return PathBuf::from(config).join("kyth/preset.toml"); }
    PathBuf::from(std::env::var_os("HOME").unwrap_or_else(|| ".".into())).join(".config/kyth/preset.toml")
}

fn strings(value: Option<&toml::Value>, fallback: &[String]) -> Vec<String> {
    value.and_then(toml::Value::as_array).map(|items| items.iter().filter_map(toml::Value::as_str).map(String::from).collect()).unwrap_or_else(|| fallback.to_vec())
}

pub fn load(path: impl AsRef<Path>) -> RolePreset {
    let Ok(raw) = std::fs::read_to_string(path) else { return RolePreset::default(); };
    let Ok(value) = raw.parse::<toml::Value>() else { return RolePreset::default(); };
    let profile = Role::parse(value.get("profile").and_then(toml::Value::as_str));
    let defaults = values(profile);
    RolePreset {
        profile,
        flatpaks: strings(value.get("flatpaks"), &defaults.flatpaks),
        distroboxes: strings(value.get("distroboxes"), &defaults.distroboxes),
        vscode_extensions: strings(value.get("vscode_extensions"), &defaults.vscode_extensions),
    }
}

fn array(values: &[String]) -> String { format!("[{}]", values.iter().map(|value| format!("{value:?}")).collect::<Vec<_>>().join(", ")) }

pub fn save(path: impl AsRef<Path>, preset: &RolePreset) -> std::io::Result<()> {
    let text = format!("profile = {:?}\nflatpaks = {}\ndistroboxes = {}\nvscode_extensions = {}\n", preset.profile.as_str(), array(&preset.flatpaks), array(&preset.distroboxes), array(&preset.vscode_extensions));
    crate::atomic_io::atomic_write_text(path, &text, Some(0o600))
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn supplies_role_defaults_and_unknown_profile_falls_back() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("preset.toml");
        std::fs::write(&path, "profile = \"dev\"\n").unwrap();
        let preset = load(&path);
        assert_eq!(preset.profile, Role::Dev);
        assert_eq!(preset.distroboxes, vec!["kyth-ai-dev"]);
        assert_eq!(Role::parse(Some("unknown")), Role::Everyday);
    }

    #[test]
    fn preserves_explicit_lists_and_round_trips() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("preset.toml");
        let preset = RolePreset { profile: Role::Creator, flatpaks: vec!["org.example.App".into()], distroboxes: vec![], vscode_extensions: vec!["rust-lang.rust-analyzer".into()] };
        save(&path, &preset).unwrap();
        assert_eq!(load(&path), preset);
    }
}
