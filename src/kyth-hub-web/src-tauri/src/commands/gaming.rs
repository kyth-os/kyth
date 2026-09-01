//! Gaming section bridge: the tool grid (install/launch/uninstall), the
//! Discord/OBS one-shot capture fixes, and the two "open a well-known
//! folder" actions from the first-failure playbook / Fix My Game card.
//! Catalog and command builders live in `kyth_shared::system::gaming_tools`.

use std::process::Command;
use std::time::Duration;

use serde::Serialize;

use kyth_shared::system::gaming_tools::{self, GAMING_TOOLS};

use super::job::{failure_detail, spawn_argv_job, start_job};

#[derive(Serialize)]
pub(crate) struct GamingToolResponse {
    flatpak: String,
    name: String,
    desc: String,
    installed: bool,
}

#[tauri::command]
pub(crate) fn gaming_tools() -> Vec<GamingToolResponse> {
    GAMING_TOOLS
        .iter()
        .map(|tool| GamingToolResponse {
            flatpak: tool.flatpak.to_string(),
            name: tool.name.to_string(),
            desc: tool.desc.to_string(),
            installed: kyth_shared::system::software_catalog::is_flatpak_installed(tool.flatpak),
        })
        .collect()
}

fn validated_gaming_tool(flatpak_id: &str) -> Result<&'static gaming_tools::GamingTool, String> {
    gaming_tools::find_gaming_tool(flatpak_id).ok_or_else(|| "unknown gaming tool".to_string())
}

#[tauri::command]
pub(crate) fn gaming_tool_install(flatpak_id: String) -> Result<String, String> {
    let tool = validated_gaming_tool(&flatpak_id)?;
    let name = tool.name.to_string();
    let argv = vec![
        "bash".to_string(),
        "-c".to_string(),
        format!(
            "flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo && flatpak install -y flathub {flatpak_id}"
        ),
    ];
    let job = start_job("gaming-install", &format!("Installing {name}…"))?;
    spawn_argv_job(job.clone(), argv, Duration::from_secs(600), move |result| match result {
        Ok(output) if output.status.success() => ("complete".to_string(), format!("{name} installed.")),
        Ok(output) => ("failed".to_string(), failure_detail("Installation", &output)),
        Err(err) => ("failed".to_string(), format!("Could not start installation: {err}")),
    });
    Ok(job)
}

#[tauri::command]
pub(crate) fn gaming_tool_uninstall(flatpak_id: String) -> Result<String, String> {
    let tool = validated_gaming_tool(&flatpak_id)?;
    let name = tool.name.to_string();
    let argv = vec!["flatpak".to_string(), "uninstall".to_string(), "-y".to_string(), flatpak_id];
    let job = start_job("gaming-uninstall", &format!("Uninstalling {name}…"))?;
    spawn_argv_job(job.clone(), argv, Duration::from_secs(120), move |result| match result {
        Ok(output) if output.status.success() => ("complete".to_string(), format!("{name} uninstalled.")),
        Ok(output) => ("failed".to_string(), failure_detail("Uninstall", &output)),
        Err(err) => ("failed".to_string(), format!("Could not start uninstall: {err}")),
    });
    Ok(job)
}

#[tauri::command]
pub(crate) fn gaming_tool_launch(flatpak_id: String) -> Result<String, String> {
    let tool = validated_gaming_tool(&flatpak_id)?;
    Command::new(tool.launch[0])
        .args(&tool.launch[1..])
        .spawn()
        .map_err(|err| format!("could not launch {}: {err}", tool.name))?;
    Ok(format!("{} launched.", tool.name))
}

#[tauri::command]
pub(crate) fn gaming_job_status(job: String) -> crate::InstallStatus {
    super::job::job_status(job)
}

/// One-shot Flatpak permission repairs — bounded, `--user`-scoped, no sudo.
/// Fast enough to run synchronously rather than as a background job, same
/// as `apply_pipewire_quantum`/`apply_plasma_preset`.
fn run_capture_fix(action: &str, argv: Vec<String>) -> Result<String, String> {
    let mut command = Command::new(&argv[0]);
    command.args(&argv[1..]);
    match kyth_shared::system::process::run_bounded_command(command, Duration::from_secs(10)) {
        Ok(output) if output.status.success() => Ok(format!("{action} applied. Restart the app to take effect.")),
        Ok(output) => Err(failure_detail(action, &output)),
        Err(err) => Err(format!("Could not run {action}: {err}")),
    }
}

#[tauri::command]
pub(crate) fn fix_discord_screenshare() -> Result<String, String> {
    run_capture_fix("Discord screen share repair", gaming_tools::discord_screenshare_fix_command())
}

#[tauri::command]
pub(crate) fn fix_obs_pipewire() -> Result<String, String> {
    run_capture_fix("OBS capture repair", gaming_tools::obs_pipewire_fix_command())
}

#[tauri::command]
pub(crate) fn prefix_reset_hint() -> String {
    gaming_tools::prefix_reset_hint().to_string()
}

#[tauri::command]
pub(crate) fn support_snapshot_command() -> String {
    gaming_tools::support_snapshot_command().to_string()
}

/// Opens one of the two well-known game-data folders in the desktop file
/// manager. `key` is validated against `game_folder_path`'s fixed set —
/// never an arbitrary caller-supplied path.
#[tauri::command]
pub(crate) fn open_game_folder(key: String) -> Result<String, String> {
    let raw = gaming_tools::game_folder_path(&key).ok_or_else(|| "unknown folder".to_string())?;
    let home = std::env::var("HOME").map_err(|_| "HOME is not set".to_string())?;
    let expanded = raw.replacen('~', &home, 1);
    if !std::path::Path::new(&expanded).exists() {
        return Err(format!("Folder not found yet: {expanded}"));
    }
    Command::new("xdg-open")
        .arg(&expanded)
        .spawn()
        .map_err(|err| format!("could not open {expanded}: {err}"))?;
    Ok(format!("Opened {expanded}"))
}
