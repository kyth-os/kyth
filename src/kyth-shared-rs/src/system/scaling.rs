//! Offline fractional display-scaling configuration.
//!
//! This ports the data and projection half of `kyth_shared.scaling`.
//! KScreen discovery, ICC deployment, and display mutation stay outside the
//! shared crate because they are guarded desktop actions.

use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq)]
pub struct ScalingOutput {
    pub scale: f64,
    pub icc: String,
}

pub type ScalingConfig = BTreeMap<String, ScalingOutput>;

pub fn config_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path {
        return path.as_ref().to_path_buf();
    }
    let base = std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".config")))
        .unwrap_or_else(|| PathBuf::from(".config"));
    base.join("kyth/scaling.toml")
}

fn parse_scale(value: Option<&toml::Value>) -> f64 {
    value
        .and_then(|value| value.as_float().or_else(|| value.as_integer().map(|value| value as f64)))
        .unwrap_or(1.0)
        .clamp(1.0, 3.0)
}

pub fn load(path: impl AsRef<Path>) -> ScalingConfig {
    let Ok(raw) = std::fs::read_to_string(path) else {
        return ScalingConfig::new();
    };
    let Ok(value) = raw.parse::<toml::Value>() else {
        return ScalingConfig::new();
    };
    value
        .get("outputs")
        .and_then(toml::Value::as_table)
        .map(|outputs| {
            outputs
                .iter()
                .filter_map(|(name, value)| {
                    let table = value.as_table()?;
                    Some((
                        name.clone(),
                        ScalingOutput {
                            scale: parse_scale(table.get("scale")),
                            icc: table.get("icc").and_then(toml::Value::as_str).unwrap_or_default().to_string(),
                        },
                    ))
                })
                .collect()
        })
        .unwrap_or_default()
}

pub fn save(path: impl AsRef<Path>, outputs: &ScalingConfig) -> std::io::Result<()> {
    let quote = |value: &str| toml::Value::String(value.to_string()).to_string();
    let mut lines = vec!["# Kyth scaling per-output".to_string(), String::new()];
    for (name, output) in outputs {
        lines.push(format!("[outputs.{}]", quote(name)));
        lines.push(format!("scale = {}", output.scale));
        if !output.icc.is_empty() {
            lines.push(format!("icc = {}", quote(&output.icc)));
        }
        lines.push(String::new());
    }
    crate::atomic_io::atomic_write_text(path, &format!("{}\n", lines.join("\n")), Some(0o600))
}

pub fn kwin_config(outputs: &ScalingConfig) -> Value {
    json!({
        "outputs": outputs.iter().map(|(name, output)| json!({
            "name": name,
            "scale": output.scale,
            "icc": output.icc,
        })).collect::<Vec<_>>()
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn loads_clamped_scaling_and_projects_kwin_data() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("scaling.toml");
        std::fs::write(&path, "[outputs.\"DP-1\"]\nscale = 4\nicc = \"/tmp/display.icc\"\n").unwrap();
        let config = load(&path);
        assert_eq!(config["DP-1"].scale, 3.0);
        assert_eq!(kwin_config(&config)["outputs"][0]["name"], "DP-1");
    }

    #[test]
    fn saves_sorted_outputs_and_round_trips() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("nested/scaling.toml");
        let config = ScalingConfig::from([
            ("HDMI-1".into(), ScalingOutput { scale: 1.25, icc: String::new() }),
            ("DP-1".into(), ScalingOutput { scale: 2.0, icc: "/tmp/a.icc".into() }),
        ]);
        save(&path, &config).unwrap();
        let loaded = load(&path);
        assert_eq!(loaded["DP-1"].icc, "/tmp/a.icc");
        assert_eq!(loaded["HDMI-1"].scale, 1.25);
    }
}
