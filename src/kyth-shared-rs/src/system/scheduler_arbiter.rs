//! Pure scheduler-arbiter configuration and desired-state calculation.
//!
//! The Python arbiter is the single writer for SCX/BORE placement. This
//! module ports the policy boundary only: service/process detection,
//! gamemode.ini rewriting, and activation remain caller-owned.

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::path::Path;

pub const DEFAULT_CONFIG_PATH: &str = "/etc/kyth/sched-arbiter.toml";
pub const DEFAULT_FLAG_PATH: &str = "/run/kyth/sched-arbiter.json";

const VALID_CHOICES: [&str; 4] = ["auto", "scx_rusty", "bore", "balanced"];

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ArbiterConfig {
    pub chosen: String,
    pub allow_ananicy_pin: bool,
    pub gamemode_pin: bool,
}

impl Default for ArbiterConfig {
    fn default() -> Self {
        Self {
            chosen: "auto".into(),
            allow_ananicy_pin: false,
            gamemode_pin: false,
        }
    }
}

impl ArbiterConfig {
    pub fn normalized(chosen: impl AsRef<str>, allow_ananicy_pin: bool, gamemode_pin: bool) -> Self {
        let mut chosen = chosen.as_ref().to_ascii_lowercase();
        if chosen == "none" {
            chosen = "balanced".into();
        }
        if !VALID_CHOICES.contains(&chosen.as_str()) {
            chosen = "auto".into();
        }
        Self { chosen, allow_ananicy_pin, gamemode_pin }
    }

    pub fn from_value(value: &Value) -> Self {
        let object = value.as_object();
        Self::normalized(
            object.and_then(|map| map.get("chosen")).and_then(Value::as_str).unwrap_or("auto"),
            object.and_then(|map| map.get("allow_ananicy_pin")).and_then(Value::as_bool).unwrap_or(false),
            object.and_then(|map| map.get("gamemode_pin")).and_then(Value::as_bool).unwrap_or(false),
        )
    }

    pub fn load(path: impl AsRef<Path>) -> Self {
        std::fs::read_to_string(path)
            .ok()
            .and_then(|text| toml::from_str::<toml::Value>(&text).ok())
            .map(|value| Self::from_value(&toml_to_json(&value)))
            .unwrap_or_default()
    }

    pub fn to_toml(&self) -> String {
        format!(
            "# Kyth scheduler arbiter — single writer for placement\n\
             # chosen: auto (detect SCX), scx_rusty, bore, balanced\n\
             chosen = \"{}\"\n\
             allow_ananicy_pin = {}\n\
             gamemode_pin = {}\n",
            self.chosen, self.allow_ananicy_pin, self.gamemode_pin
        )
    }

    pub fn as_value(&self) -> Value {
        json!({
            "chosen": self.chosen,
            "allow_ananicy_pin": self.allow_ananicy_pin,
            "gamemode_pin": self.gamemode_pin,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DesiredState {
    pub chosen: String,
    pub active: String,
    pub scx_active: bool,
    pub bore_available: bool,
    pub gamemode_pin: bool,
    pub allow_ananicy_pin: bool,
}

pub fn desired_state(config: &ArbiterConfig, scx_active: bool, bore_available: bool) -> DesiredState {
    let active = match config.chosen.as_str() {
        "auto" if scx_active => "scx_rusty",
        "auto" if bore_available => "bore",
        "auto" => "balanced",
        chosen => chosen,
    };
    let (gamemode_pin, allow_ananicy_pin) = if active == "scx_rusty" || scx_active {
        (false, false)
    } else if active == "bore" {
        (config.gamemode_pin, config.allow_ananicy_pin)
    } else {
        (false, false)
    };
    DesiredState {
        chosen: config.chosen.clone(),
        active: active.into(),
        scx_active,
        bore_available,
        gamemode_pin,
        allow_ananicy_pin,
    }
}

impl DesiredState {
    pub fn as_value(&self) -> Value {
        json!({
            "chosen": self.chosen,
            "active": self.active,
            "scx_active": self.scx_active,
            "bore_available": self.bore_available,
            "gamemode_pin": self.gamemode_pin,
            "allow_ananicy_pin": self.allow_ananicy_pin,
        })
    }
}

pub fn active_from_flag(value: &Value) -> String {
    value
        .get("active")
        .and_then(Value::as_str)
        .unwrap_or("unknown")
        .to_string()
}

fn toml_to_json(value: &toml::Value) -> Value {
    match value {
        toml::Value::String(value) => Value::String(value.clone()),
        toml::Value::Integer(value) => json!(value),
        toml::Value::Float(value) => json!(value),
        toml::Value::Boolean(value) => Value::Bool(*value),
        toml::Value::Datetime(value) => Value::String(value.to_string()),
        toml::Value::Array(values) => Value::Array(values.iter().map(toml_to_json).collect()),
        toml::Value::Table(values) => Value::Object(
            values.iter().map(|(key, value)| (key.clone(), toml_to_json(value))).collect(),
        ),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalizes_legacy_and_unknown_choices() {
        assert_eq!(ArbiterConfig::normalized("NONE", true, true).chosen, "balanced");
        assert_eq!(ArbiterConfig::normalized("surprise", true, true).chosen, "auto");
        assert_eq!(ArbiterConfig::default(), ArbiterConfig::normalized("auto", false, false));
    }

    #[test]
    fn loads_toml_and_round_trips_projection() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("sched-arbiter.toml");
        std::fs::write(&path, "chosen = \"bore\"\nallow_ananicy_pin = true\ngamemode_pin = true\n").unwrap();
        let config = ArbiterConfig::load(&path);
        assert_eq!(config.chosen, "bore");
        assert!(config.allow_ananicy_pin);
        assert!(config.to_toml().contains("gamemode_pin = true"));
    }

    #[test]
    fn auto_selects_single_writer_and_disables_competing_pinning() {
        let config = ArbiterConfig::normalized("auto", true, true);
        let scx = desired_state(&config, true, true);
        assert_eq!(scx.active, "scx_rusty");
        assert!(!scx.gamemode_pin);
        assert!(!scx.allow_ananicy_pin);

        let bore = desired_state(&config, false, true);
        assert_eq!(bore.active, "bore");
        assert!(bore.gamemode_pin);
        assert!(bore.allow_ananicy_pin);

        let balanced = desired_state(&config, false, false);
        assert_eq!(balanced.active, "balanced");
        assert!(!balanced.gamemode_pin);
    }

    #[test]
    fn explicit_bore_still_yields_to_active_scx() {
        let config = ArbiterConfig::normalized("bore", true, true);
        let state = desired_state(&config, true, false);
        assert_eq!(state.active, "bore");
        assert!(!state.gamemode_pin);
        assert!(!state.allow_ananicy_pin);
    }

    #[test]
    fn flag_status_has_safe_unknown_fallback() {
        assert_eq!(active_from_flag(&json!({"active":"scx_rusty"})), "scx_rusty");
        assert_eq!(active_from_flag(&json!({})), "unknown");
    }
}
