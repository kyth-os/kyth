//! Safe setup-transfer manifest validation and preview data.
//!
//! Archive extraction and restoration remain explicit, guarded operations in
//! the existing helper. This module owns only the format contract and path
//! allowlist so native clients can inspect an archive manifest safely.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::{Component, Path};

pub const ARCHIVE_VERSION: u64 = 1;
pub const ARCHIVE_PREFIX: &str = "kyth-setup";

pub const CONFIG_PATHS: &[&str] = &[
    ".config/kdeglobals",
    ".config/kglobalshortcutsrc",
    ".config/kwinrc",
    ".config/kwinrulesrc",
    ".config/kcminputrc",
    ".config/kscreenlockerrc",
    ".config/klipperrc",
    ".config/plasmarc",
    ".config/powerdevilrc",
    ".config/spectaclerc",
    ".config/konsolerc",
    ".config/kwalletrc",
    ".config/kyth-cloud-sync.json",
    ".config/kyth-dynamic-lock.json",
    ".config/kyth-smb-shares.json",
    ".config/MangoHud",
    ".config/vkBasalt",
    ".local/share/kyth/profile",
];

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct SetupFlatpak {
    #[serde(default)]
    pub id: String,
    #[serde(default)]
    pub origin: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct SetupManifest {
    pub format: String,
    pub version: u64,
    #[serde(default)]
    pub created: String,
    #[serde(default)]
    pub hostname: String,
    #[serde(default)]
    pub flatpaks: Vec<SetupFlatpak>,
    #[serde(default)]
    pub default_apps: BTreeMap<String, String>,
    #[serde(default)]
    pub cloud_remotes: Vec<Value>,
    pub copied_paths: Vec<String>,
    #[serde(default)]
    pub secrets_excluded: Vec<String>,
}

pub fn is_allowed_restore_path(relative: &str) -> bool {
    let path = Path::new(relative);
    if path.is_absolute() || path.components().any(|component| matches!(component, Component::ParentDir)) {
        return false;
    }
    if CONFIG_PATHS.contains(&relative) {
        return true;
    }
    let components = path.components().collect::<Vec<_>>();
    components.len() == 4
        && components[0].as_os_str() == ".local"
        && components[1].as_os_str() == "share"
        && components[2].as_os_str() == "applications"
        && components[3].as_os_str().to_string_lossy().starts_with("kyth-")
        && components[3].as_os_str().to_string_lossy().ends_with(".desktop")
}

pub fn validate_manifest(value: &Value) -> Result<SetupManifest, String> {
    let object = value.as_object().ok_or_else(|| "The setup archive manifest is invalid.".to_string())?;
    if object.get("format").and_then(Value::as_str) != Some("KythOS setup transfer") {
        return Err("This is not a KythOS setup archive.".to_string());
    }
    if object.get("version").and_then(Value::as_u64) != Some(ARCHIVE_VERSION) {
        return Err(format!("Unsupported setup archive version: {}", object.get("version").unwrap_or(&Value::Null)));
    }
    let copied = object.get("copied_paths").and_then(Value::as_array).ok_or_else(|| "The setup archive contains an unsupported settings path.".to_string())?;
    if !copied.iter().all(|path| path.as_str().is_some_and(is_allowed_restore_path)) {
        return Err("The setup archive contains an unsupported settings path.".to_string());
    }
    serde_json::from_value(value.clone()).map_err(|_| "The setup archive manifest is malformed.".to_string())
}

pub fn preview_summary(manifest: &SetupManifest) -> String {
    let flatpaks = manifest.flatpaks.len();
    let settings = manifest.copied_paths.len();
    let remotes = manifest.cloud_remotes.len();
    format!(
        "Created {} on {}\n{} Flatpak apps, {} settings paths, {} cloud definitions\nPasswords and login tokens are excluded. Network shares and cloud accounts will need reauthentication.",
        if manifest.created.is_empty() { "unknown" } else { &manifest.created },
        if manifest.hostname.is_empty() { "unknown" } else { &manifest.hostname },
        flatpaks,
        settings,
        remotes,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn manifest(paths: &[&str]) -> Value {
        serde_json::json!({
            "format": "KythOS setup transfer", "version": 1,
            "created": "2026-08-29T00:00:00+00:00", "hostname": "kyth-live",
            "flatpaks": [{"id":"org.example.App","origin":"flathub"}],
            "default_apps": {"text/plain":"org.kde.kwrite.desktop"},
            "cloud_remotes": [{"name":"drive","type":"webdav"}],
            "copied_paths": paths, "secrets_excluded": ["KWallet contents"]
        })
    }

    #[test]
    fn validates_manifest_and_renders_preview() {
        let value = manifest(&[".config/kdeglobals", ".local/share/applications/kyth-demo.desktop"]);
        let parsed = validate_manifest(&value).unwrap();
        assert_eq!(parsed.flatpaks[0].id, "org.example.App");
        assert!(preview_summary(&parsed).contains("1 Flatpak apps, 2 settings paths"));
    }

    #[test]
    fn rejects_traversal_and_unowned_desktop_files() {
        assert!(is_allowed_restore_path(".config/kdeglobals"));
        assert!(is_allowed_restore_path(".local/share/applications/kyth-demo.desktop"));
        assert!(!is_allowed_restore_path("../.config/kdeglobals"));
        assert!(!is_allowed_restore_path(".local/share/applications/other.desktop"));
        assert!(!is_allowed_restore_path(".local/share/applications/kyth-demo.desktop/extra"));
        assert!(validate_manifest(&manifest(&[".config/unknown"])).is_err());
    }

    #[test]
    fn rejects_wrong_format_and_version() {
        let mut wrong_format = manifest(&[]);
        wrong_format["format"] = "other".into();
        assert!(validate_manifest(&wrong_format).unwrap_err().contains("not a KythOS"));
        let mut wrong_version = manifest(&[]);
        wrong_version["version"] = 2.into();
        assert!(validate_manifest(&wrong_version).unwrap_err().contains("Unsupported"));
    }
}
