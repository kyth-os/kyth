//! Port of `kyth_shared.gaming_per_game` — the per-game HDR/latency profile
//! store the Gaming section's profile builder reads and writes. Persists to
//! `~/.config/kyth/gaming-per-game.toml` (Rust is the sole writer; no Python
//! twin exists for this file). Not ported:
//! `gaming_launch_env_for_appid`'s dynamic fallback-import env resolution —
//! that's for the actual game-launch path, not the builder UI this backs.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

const KNOWN_PROFILES: [&str; 7] = [
    "low-latency",
    "balanced",
    "battery",
    "quality",
    "hdr",
    "sharp",
    "latency",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GameProfile {
    pub profile: String,
    pub hdr: bool,
    /// FPS cap as decimal text ("" = none). Validated on load/save.
    pub fps: String,
    /// Render on the NVIDIA dGPU via PRIME offload (hybrid laptops).
    pub prime: bool,
}

impl Default for GameProfile {
    fn default() -> Self {
        Self {
            profile: "balanced".to_string(),
            hdr: false,
            fps: String::new(),
            prime: false,
        }
    }
}

/// FPS caps are short decimals the `--fps` flag accepts. Anything else
/// loads/saves as uncapped rather than erroring a whole profile.
pub fn normalize_fps(value: &str) -> String {
    let trimmed = value.trim();
    if !trimmed.is_empty()
        && trimmed.len() <= 4
        && trimmed.bytes().all(|byte| byte.is_ascii_digit())
        && trimmed
            .parse::<u32>()
            .is_ok_and(|fps| fps > 0 && fps <= 999)
    {
        trimmed.to_string()
    } else {
        String::new()
    }
}

pub fn per_game_config_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path {
        return path.as_ref().to_path_buf();
    }
    if let Some(config) = std::env::var_os("XDG_CONFIG_HOME") {
        return PathBuf::from(config).join("kyth/gaming-per-game.toml");
    }
    PathBuf::from(std::env::var_os("HOME").unwrap_or_else(|| ".".into()))
        .join(".config/kyth/gaming-per-game.toml")
}

pub fn load_per_game_config(path: impl AsRef<Path>) -> BTreeMap<String, GameProfile> {
    let Ok(raw) = std::fs::read_to_string(path) else {
        return BTreeMap::new();
    };
    let Ok(value) = raw.parse::<toml::Value>() else {
        return BTreeMap::new();
    };
    let Some(games) = value.get("games").and_then(toml::Value::as_table) else {
        return BTreeMap::new();
    };
    games
        .iter()
        .filter_map(|(appid, entry)| {
            let entry = entry.as_table()?;
            let mut profile = entry
                .get("profile")
                .and_then(toml::Value::as_str)
                .unwrap_or("balanced")
                .to_string();
            if !KNOWN_PROFILES.contains(&profile.as_str()) {
                profile = "balanced".to_string();
            }
            let hdr = entry
                .get("hdr")
                .and_then(toml::Value::as_bool)
                .unwrap_or(false);
            let fps = entry
                .get("fps")
                .and_then(toml::Value::as_str)
                .map(normalize_fps)
                .unwrap_or_default();
            let prime = entry
                .get("prime")
                .and_then(toml::Value::as_bool)
                .unwrap_or(false);
            Some((
                appid.clone(),
                GameProfile {
                    profile,
                    hdr,
                    fps,
                    prime,
                },
            ))
        })
        .collect()
}

/// Hand-built TOML text, matching Python's own hand-built writer exactly
/// (rather than a library serializer, which could format `[games."id"]`
/// sections differently) — both sides read/write the same file format
/// while this store is additive, not yet the sole writer.
pub fn save_per_game_config(
    games: &BTreeMap<String, GameProfile>,
    path: impl AsRef<Path>,
) -> std::io::Result<()> {
    let mut lines = vec!["# Kyth per-game gaming config — HDR + latency profile".to_string()];
    for (appid, entry) in games {
        lines.push(format!("[games.\"{appid}\"]"));
        lines.push(format!("profile = \"{}\"", entry.profile));
        lines.push(format!("hdr = {}", entry.hdr));
        if !entry.fps.is_empty() {
            lines.push(format!("fps = \"{}\"", entry.fps));
        }
        if entry.prime {
            lines.push("prime = true".to_string());
        }
        lines.push(String::new());
    }
    crate::atomic_io::atomic_write_bytes(path, lines.join("\n").as_bytes(), None)
}

pub fn get_profile_for_appid(appid: &str, path: impl AsRef<Path>) -> GameProfile {
    load_per_game_config(path).remove(appid).unwrap_or_default()
}

pub fn set_profile_for_appid(
    appid: &str,
    profile: &str,
    hdr: bool,
    fps: &str,
    prime: bool,
    path: impl AsRef<Path>,
) -> std::io::Result<()> {
    let mut games = load_per_game_config(&path);
    games.insert(
        appid.to_string(),
        GameProfile {
            profile: profile.to_string(),
            hdr,
            fps: normalize_fps(fps),
            prime,
        },
    );
    save_per_game_config(&games, path)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn missing_file_loads_empty() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("gaming-per-game.toml");
        assert!(load_per_game_config(&path).is_empty());
    }

    #[test]
    fn round_trips_a_saved_profile() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("gaming-per-game.toml");
        set_profile_for_appid("730", "hdr", true, "144", true, &path).unwrap();
        let loaded = get_profile_for_appid("730", &path);
        assert_eq!(
            loaded,
            GameProfile {
                profile: "hdr".to_string(),
                hdr: true,
                fps: "144".to_string(),
                prime: true,
            }
        );
    }

    #[test]
    fn unknown_profile_falls_back_to_balanced() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("gaming-per-game.toml");
        std::fs::write(
            &path,
            "[games.\"1\"]\nprofile = \"not-a-real-profile\"\nhdr = false\n",
        )
        .unwrap();
        assert_eq!(get_profile_for_appid("1", &path).profile, "balanced");
    }

    #[test]
    fn setting_one_appid_does_not_disturb_another() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("gaming-per-game.toml");
        set_profile_for_appid("1", "quality", false, "", false, &path).unwrap();
        set_profile_for_appid("2", "latency", true, "60", false, &path).unwrap();
        let games = load_per_game_config(&path);
        assert_eq!(games.len(), 2);
        assert_eq!(
            games["1"],
            GameProfile {
                profile: "quality".to_string(),
                hdr: false,
                fps: String::new(),
                prime: false,
            }
        );
        assert_eq!(
            games["2"],
            GameProfile {
                profile: "latency".to_string(),
                hdr: true,
                fps: "60".to_string(),
                prime: false,
            }
        );
    }

    #[test]
    fn fps_normalizes_to_caps_or_empty() {
        assert_eq!(normalize_fps("144"), "144");
        assert_eq!(normalize_fps(" 60 "), "60");
        assert_eq!(normalize_fps(""), "");
        assert_eq!(normalize_fps("144hz"), "");
        assert_eq!(normalize_fps("10000"), "");
        assert_eq!(normalize_fps("0"), "");
    }

    #[test]
    fn path_prefers_explicit_then_xdg_config_home() {
        assert_eq!(
            per_game_config_path(Some("/tmp/custom.toml")),
            PathBuf::from("/tmp/custom.toml")
        );
    }
}
