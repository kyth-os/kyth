//! Offline third-party repository specifications.
//!
//! Rendering repository text is safe and deterministic; enabling repositories
//! or importing signing keys remains an explicit package-management action.

use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RepoSpec {
    pub name: String,
    pub description: String,
    pub baseurl: String,
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(rename = "type", default = "default_repo_type")]
    pub repo_type: String,
    #[serde(default = "default_true")]
    pub repo_gpgcheck: bool,
    #[serde(default)]
    pub gpgcheck: bool,
    #[serde(default)]
    pub gpgkey: String,
}

fn default_true() -> bool {
    true
}
fn default_repo_type() -> String {
    "rpm".into()
}

impl RepoSpec {
    /// Validate a field for safe interpolation into a .repo file.
    /// M2: newlines would allow injecting arbitrary repo directives
    /// (e.g. `gpgcheck=0`), silently disabling signature verification.
    fn validate_repo_field(name: &str, value: &str) -> Result<(), String> {
        if value.contains('\n') || value.contains('\r') {
            return Err(format!("repo field {name} must not contain newlines"));
        }
        Ok(())
    }

    pub fn render_yum_repo(&self) -> Result<String, String> {
        Self::validate_repo_field("name", &self.name)?;
        Self::validate_repo_field("description", &self.description)?;
        Self::validate_repo_field("baseurl", &self.baseurl)?;
        Self::validate_repo_field("type", &self.repo_type)?;
        Self::validate_repo_field("gpgkey", &self.gpgkey)?;
        let mut lines = vec![
            format!("[{}]", self.name),
            format!("name={}", self.description),
            format!("baseurl={}", self.baseurl),
            format!("enabled={}", i32::from(self.enabled)),
            format!("type={}", self.repo_type),
            format!("repo_gpgcheck={}", i32::from(self.repo_gpgcheck)),
            format!("gpgcheck={}", i32::from(self.gpgcheck)),
        ];
        if !self.gpgkey.is_empty() {
            lines.push(format!("gpgkey={}", self.gpgkey));
        }
        Ok(format!("{}\n", lines.join("\n")))
    }
}

pub const GAMING_COPRS: [&str; 7] = [
    "ublue-os/bazzite",
    "ublue-os/bazzite-multilib",
    "ublue-os/staging",
    "ublue-os/packages",
    "ublue-os/obs-vkcapture",
    "lukenukem/asus-linux",
    "ycollet/audinux",
];

pub fn load_repo_specs(path: impl AsRef<Path>) -> Result<Vec<RepoSpec>, String> {
    let raw = std::fs::read_to_string(path).map_err(|error| error.to_string())?;
    serde_json::from_str(&raw).map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn renders_defaults_and_optional_gpg_key() {
        let spec: RepoSpec = serde_json::from_value(serde_json::json!({
            "name": "demo", "description": "Demo repo", "baseurl": "https://example.test/rpm", "gpgkey": "https://example.test/key"
        })).unwrap();
        assert!(spec.enabled);
        assert_eq!(spec.repo_type, "rpm");
        let rendered = spec.render_yum_repo().unwrap();
        assert!(rendered.contains("repo_gpgcheck=1"));
        assert!(rendered.ends_with("gpgkey=https://example.test/key\n"));
    }

    #[test]
    fn rejects_newline_injection_in_every_interpolated_field() {
        // M2: a newline in any interpolated field could inject `gpgcheck=0`.
        for field in ["name", "description", "baseurl", "type", "gpgkey"] {
            for payload in ["evil\ngpgcheck=0", "evil\r\ngpgcheck=0"] {
                let mut value = serde_json::json!({
                    "name": "demo", "description": "Demo", "baseurl": "https://example.test",
                    "type": "rpm", "gpgkey": ""
                });
                value[field] = serde_json::Value::String(payload.to_string());
                let spec: RepoSpec = serde_json::from_value(value).unwrap();
                assert!(
                    spec.render_yum_repo().is_err(),
                    "field {field} accepted newline payload"
                );
            }
        }
    }

    #[test]
    fn rejects_section_header_injection_via_name() {
        let spec: RepoSpec = serde_json::from_value(serde_json::json!({
            "name": "x]\n[evil", "description": "Demo", "baseurl": "https://example.test"
        }))
        .unwrap();
        assert!(spec.render_yum_repo().is_err());
    }

    #[test]
    fn loads_json_specs() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("repos.json");
        std::fs::write(
            &path,
            r#"[{"name":"demo","description":"Demo","baseurl":"https://example.test"}]"#,
        )
        .unwrap();
        assert_eq!(load_repo_specs(&path).unwrap()[0].name, "demo");
    }
}
