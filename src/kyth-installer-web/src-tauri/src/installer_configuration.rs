//! Pure installed-system configuration planning.
//!
//! Passwords and account creation intentionally do not cross this model. The
//! privileged Python service continues to own account databases and all file
//! writes; this module describes only the non-secret configuration contract.

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize)]
pub(crate) struct ConfigurationInput {
    pub target_root: String,
    pub hostname: String,
    pub timezone: String,
    #[serde(default = "default_locale")]
    pub locale: String,
    #[serde(default = "default_keymap")]
    pub keymap: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(crate) struct ConfigWrite {
    pub path: String,
    pub content: String,
    pub mode: u32,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(crate) struct ConfigurationPlan {
    pub target_root: String,
    pub writes: Vec<ConfigWrite>,
    pub localtime_target: String,
    pub executor: &'static str,
}

fn default_locale() -> String { "en_US.UTF-8".to_string() }
fn default_keymap() -> String { "us".to_string() }

fn safe_component(value: &str, label: &str, allow_slash: bool) -> Result<String, String> {
    let value = value.trim();
    if value.is_empty() || value.len() > 4096 || value.contains("..") {
        return Err(format!("{label} is empty or unsafe."));
    }
    if !value.bytes().all(|byte| {
        byte.is_ascii_alphanumeric()
            || matches!(byte, b'.' | b'_' | b'@' | b'+' | b'-')
            || (allow_slash && byte == b'/')
    }) {
        return Err(format!("{label} contains unsupported characters."));
    }
    Ok(value.to_string())
}

fn safe_root(value: &str) -> Result<String, String> {
    let value = value.trim();
    if !value.starts_with('/') || value.contains("..") || value.len() > 4096 {
        return Err("target root must be an absolute safe path.".to_string());
    }
    if !value.bytes().all(|byte| {
        byte.is_ascii_alphanumeric()
            || matches!(byte, b'/' | b'.' | b'_' | b'+' | b':' | b'-')
    }) {
        return Err("target root contains unsupported characters.".to_string());
    }
    Ok(value.to_string())
}

pub(crate) fn build_plan(input: ConfigurationInput) -> Result<ConfigurationPlan, String> {
    let target_root = safe_root(&input.target_root)?;
    let hostname = safe_component(&input.hostname, "hostname", false)?;
    if hostname.starts_with('-') || hostname.ends_with('-') {
        return Err("hostname cannot start or end with '-'.".to_string());
    }
    let timezone = safe_component(&input.timezone, "timezone", true)?;
    if timezone.starts_with('/') || timezone.ends_with('/') || timezone.contains("//") {
        return Err("timezone must be a relative zoneinfo path.".to_string());
    }
    let locale = safe_component(&input.locale, "locale", false)?;
    let keymap = safe_component(&input.keymap, "keymap", false)?;
    let etc = format!("{target_root}/etc");
    Ok(ConfigurationPlan {
        target_root,
        writes: vec![
            ConfigWrite { path: format!("{etc}/hostname"), content: format!("{hostname}\n"), mode: 0o644 },
            ConfigWrite { path: format!("{etc}/locale.conf"), content: format!("LANG={locale}\n"), mode: 0o644 },
            ConfigWrite { path: format!("{etc}/vconsole.conf"), content: format!("KEYMAP={keymap}\n"), mode: 0o644 },
        ],
        localtime_target: format!("/usr/share/zoneinfo/{timezone}"),
        executor: "kyth-installerd",
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plans_non_secret_installed_configuration() {
        let plan = build_plan(ConfigurationInput {
            target_root: "/mnt/target".to_string(),
            hostname: "kyth-box".to_string(),
            timezone: "Europe/Berlin".to_string(),
            locale: "en_US.UTF-8".to_string(),
            keymap: "us".to_string(),
        }).expect("configuration should validate");
        assert_eq!(plan.writes.len(), 3);
        assert!(plan.writes.iter().any(|write| write.content == "kyth-box\n"));
        assert_eq!(plan.localtime_target, "/usr/share/zoneinfo/Europe/Berlin");
    }

    #[test]
    fn rejects_path_traversal_and_invalid_identity_values() {
        let base = ConfigurationInput {
            target_root: "/mnt/target".to_string(),
            hostname: "kyth".to_string(),
            timezone: "UTC".to_string(),
            locale: "en_US.UTF-8".to_string(),
            keymap: "us".to_string(),
        };
        assert!(build_plan(ConfigurationInput { target_root: "/mnt/../etc".to_string(), ..base.clone() }).is_err());
        assert!(build_plan(ConfigurationInput { hostname: "bad name".to_string(), ..base.clone() }).is_err());
        assert!(build_plan(ConfigurationInput { timezone: "../UTC".to_string(), ..base }).is_err());
    }
}
