//! Small, honest gaming compatibility helpers for the Hub.
use serde::Serialize;
use std::time::Duration;

#[derive(Debug, Clone, Serialize)]
pub struct ProtonDbResult {
    pub app_id: String,
    pub tier: String,
    pub detail: String,
}

pub fn protondb_lookup(app_id: &str) -> Option<ProtonDbResult> {
    if app_id.len() > 12 || !app_id.chars().all(|c| c.is_ascii_digit()) {
        return None;
    }
    let url = format!("https://www.protondb.com/api/v1/reports/summaries/{app_id}.json");
    let argv = [
        "curl".to_string(),
        "-fsSL".to_string(),
        "--max-time".to_string(),
        "6".to_string(),
        url,
    ];
    let output = crate::system::process::run_bounded(&argv, Duration::from_secs(8)).ok()?;
    if !output.status.success() {
        return None;
    }
    let json: serde_json::Value = serde_json::from_slice(&output.stdout).ok()?;
    let tier = json.get("tier")?.as_str()?.to_string();
    Some(ProtonDbResult {
        app_id: app_id.to_string(),
        detail: format!("ProtonDB rating: {tier}"),
        tier,
    })
}

pub fn protondb_lookup_many(app_ids: &[String]) -> Vec<ProtonDbResult> {
    // The Hub UI sends at most 20 ids; clamp here too so a buggy caller
    // cannot park a sync Tauri worker on minutes of sequential lookups.
    // Each lookup is already bounded at 8s, so the worst case is ~160s.
    app_ids
        .iter()
        .take(20)
        .filter_map(|id| protondb_lookup(id))
        .take(20)
        .collect()
}

#[derive(Debug, Clone, Serialize)]
pub struct AntiCheatEntry {
    pub game: String,
    pub status: String,
    pub detail: String,
}

pub fn anti_cheat_table() -> Vec<AntiCheatEntry> {
    vec![
        AntiCheatEntry { game: "Easy Anti-Cheat".into(), status: "title-dependent".into(), detail: "Linux support must be enabled by the game developer; Proton cannot enable it globally.".into() },
        AntiCheatEntry { game: "BattlEye".into(), status: "title-dependent".into(), detail: "Some Proton titles work when the developer opts in; check the specific game.".into() },
        AntiCheatEntry { game: "Kernel anti-cheat".into(), status: "blocked".into(), detail: "Windows kernel drivers do not run through Proton.".into() },
        AntiCheatEntry { game: "Valve Anti-Cheat".into(), status: "varies".into(), detail: "Check the title's ProtonDB reports and current Steam compatibility notes.".into() },
    ]
}

/// Steam Play default status, read from Steam's own config.vdf. Read-only:
/// editing VDF while Steam runs corrupts it, so the Hub instructs and
/// verifies instead of writing.
#[derive(Debug, Clone, Serialize)]
pub struct SteamPlayStatus {
    pub steam_present: bool,
    pub steam_running: bool,
    pub mapping_present: bool,
    pub detail: String,
}

pub fn steam_config_vdf(home: &std::path::Path) -> std::path::PathBuf {
    home.join(".var/app/com.valvesoftware.Steam/.local/share/Steam/config/config.vdf")
}

pub fn steam_running() -> bool {
    crate::system::process::run_bounded(
        &["pgrep".to_string(), "-x".to_string(), "steam".to_string()],
        Duration::from_secs(5),
    )
    .map(|output| output.status.success())
    .unwrap_or(false)
}

pub fn steam_play_status(home: &std::path::Path) -> SteamPlayStatus {
    let vdf = steam_config_vdf(home);
    let steam_present = vdf.exists();
    if !steam_present {
        return SteamPlayStatus {
            steam_present: false,
            steam_running: false,
            mapping_present: false,
            detail: "Steam is not installed yet.".to_string(),
        };
    }
    let running = steam_running();
    let text = std::fs::read_to_string(&vdf).unwrap_or_default();
    // A global default mapping appears as a CompatToolMapping section with a
    // "0" (all-titles) entry. Textual scan only — the Hub never writes VDF.
    let mapping_present = text.contains("CompatToolMapping") && text.contains("\"0\"");
    let detail = if mapping_present {
        "Steam Play is enabled for all titles.".to_string()
    } else if running {
        "Quit Steam, then open Steam → Settings → Compatibility → “Enable Steam Play for all other titles”.".to_string()
    } else {
        "Open Steam → Settings → Compatibility → “Enable Steam Play for all other titles”."
            .to_string()
    };
    SteamPlayStatus {
        steam_present,
        steam_running: running,
        mapping_present,
        detail,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn missing_steam_reports_not_present() {
        let directory = tempdir().unwrap();
        let status = steam_play_status(directory.path());
        assert!(!status.steam_present && !status.mapping_present);
    }

    #[test]
    fn global_mapping_detected_in_vdf() {
        let directory = tempdir().unwrap();
        let config = steam_config_vdf(directory.path());
        fs::create_dir_all(config.parent().unwrap()).unwrap();
        fs::write(&config, "\"InstallConfigStore\"\n{\n\"Software\"\n{\n\"Valve\"\n{\n\"Steam\"\n{\n\"CompatToolMapping\"\n{\n\"0\"\n{\"name\"\"proton_experimental\"}}}}}}").unwrap();
        let status = steam_play_status(directory.path());
        assert!(status.steam_present && status.mapping_present);
    }

    #[test]
    fn vdf_without_mapping_reports_absent() {
        let directory = tempdir().unwrap();
        let config = steam_config_vdf(directory.path());
        fs::create_dir_all(config.parent().unwrap()).unwrap();
        fs::write(&config, "\"InstallConfigStore\"\n{\n\"Software\"\n{}}").unwrap();
        let status = steam_play_status(directory.path());
        assert!(status.steam_present && !status.mapping_present);
    }
}
