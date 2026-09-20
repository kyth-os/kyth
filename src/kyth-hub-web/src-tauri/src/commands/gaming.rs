//! Gaming section bridge: the tool grid (install/launch/uninstall), the
//! Discord/OBS one-shot capture fixes, the "open a well-known folder"
//! actions from the first-failure playbook / Fix My Game card, and the
//! overlay/sched-ext/per-game profile builder from
//! `page_gaming_tools_perf.py`. Catalog and command builders live in
//! `kyth_shared::system::gaming_tools`, `gaming_perf`, and `gaming_per_game`.

use std::process::Command;
use std::time::Duration;

use serde::Serialize;

use kyth_shared::system::gaming_per_game;
use kyth_shared::system::gaming_perf::{self, ProfileGoal};
use kyth_shared::system::gaming_tools::{self, GAMING_TOOLS};
use kyth_shared::system::jobs::{timeout_for, JobTimeoutClass};

use super::job::{failure_detail, spawn_argv_job, start_job};

#[derive(Serialize)]
pub(crate) struct GamingToolResponse {
    flatpak: String,
    name: String,
    desc: String,
    installed: bool,
}
#[derive(Serialize)]
pub(crate) struct GamingActionLaunch {
    pub(crate) job: String,
    pub(crate) state: String,
    pub(crate) detail: String,
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
pub(crate) fn gaming_tool_install(flatpak_id: String) -> Result<GamingActionLaunch, String> {
    let tool = validated_gaming_tool(&flatpak_id)?;
    let name = tool.name.to_string();
    let launch_detail = format!("Installing {name}…");
    let argv = vec![
        "bash".to_string(),
        "-c".to_string(),
        format!(
            "flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo && flatpak install --user -y flathub {flatpak_id}"
        ),
    ];
    let job = start_job("gaming-install", &format!("Installing {name}…"))?;
    spawn_argv_job(
        job.clone(),
        argv,
        timeout_for(JobTimeoutClass::ToolInstall),
        move |result| match result {
            Ok(output) if output.status.success() => {
                ("complete".to_string(), format!("{name} installed."))
            }
            Ok(output) => (
                "failed".to_string(),
                failure_detail("Installation", &output),
            ),
            Err(err) => (
                "failed".to_string(),
                format!("Could not start installation: {err}"),
            ),
        },
    );
    Ok(GamingActionLaunch {
        job,
        state: "running".into(),
        detail: launch_detail,
    })
}

#[tauri::command]
pub(crate) fn gaming_tool_uninstall(flatpak_id: String) -> Result<GamingActionLaunch, String> {
    let tool = validated_gaming_tool(&flatpak_id)?;
    let name = tool.name.to_string();
    let launch_detail = format!("Uninstalling {name}…");
    // Pin the user scope: an unscoped uninstall can target (or prompt for)
    // the system installation instead of the per-user one this grid manages.
    let argv = vec![
        "flatpak".to_string(),
        "uninstall".to_string(),
        "--user".to_string(),
        "-y".to_string(),
        flatpak_id,
    ];
    let job = start_job("gaming-uninstall", &format!("Uninstalling {name}…"))?;
    spawn_argv_job(
        job.clone(),
        argv,
        timeout_for(JobTimeoutClass::QuickRemove),
        move |result| match result {
            Ok(output) if output.status.success() => {
                ("complete".to_string(), format!("{name} uninstalled."))
            }
            Ok(output) => ("failed".to_string(), failure_detail("Uninstall", &output)),
            Err(err) => (
                "failed".to_string(),
                format!("Could not start uninstall: {err}"),
            ),
        },
    );
    Ok(GamingActionLaunch {
        job,
        state: "running".into(),
        detail: launch_detail,
    })
}

#[tauri::command]
pub(crate) fn gaming_tool_launch(flatpak_id: String) -> Result<String, String> {
    let tool = validated_gaming_tool(&flatpak_id)?;
    // A detached `flatpak run` of a missing app fails where nobody reads
    // it, so the old code reported "launched" for nothing. Check first.
    // (Non-Flatpak launches such as OpenRGB's native binary skip this —
    // the Flatpak inventory cannot speak for them.)
    if tool
        .launch
        .first()
        .is_some_and(|program| *program == "flatpak")
        && !kyth_shared::system::software_catalog::is_flatpak_installed(&flatpak_id)
    {
        return Err(format!("{} is not installed.", tool.name));
    }
    kyth_shared::system::process::spawn_detached(
        Command::new(tool.launch[0]).args(&tool.launch[1..]),
    )
    .map_err(|err| format!("could not launch {}: {err}", tool.name))?;
    Ok(format!("{} launched.", tool.name))
}

#[tauri::command]
pub(crate) fn gaming_job_status(job: String) -> crate::InstallStatus {
    super::job::job_status(job)
}

#[tauri::command]
pub(crate) fn gaming_job_cancel(job: String) -> crate::InstallStatus {
    super::job::cancel_job(job)
}

/// One-shot Flatpak permission repairs — bounded, `--user`-scoped, no sudo.
/// Fast enough to run synchronously rather than as a background job, same
/// as `apply_pipewire_quantum`/`apply_plasma_preset`. The 10s bound below
/// is the one intentional exception to the `JobTimeoutClass` tiers: a
/// synchronous UI-blocking call must stay well under every background tier.
/// (See the tier contract on `kyth_shared::system::jobs::timeout_for`.)
fn run_capture_fix(action: &str, argv: Vec<String>) -> Result<String, String> {
    let mut command = Command::new(&argv[0]);
    command.args(&argv[1..]);
    match kyth_shared::system::process::run_bounded_command(command, Duration::from_secs(10)) {
        Ok(output) if output.status.success() => {
            Ok(format!("{action} applied. Restart the app to take effect."))
        }
        Ok(output) => Err(failure_detail(action, &output)),
        Err(err) => Err(format!("Could not run {action}: {err}")),
    }
}

#[tauri::command]
pub(crate) fn fix_discord_screenshare() -> Result<String, String> {
    run_capture_fix(
        "Discord screen share repair",
        gaming_tools::discord_screenshare_fix_command(),
    )
}

#[tauri::command]
pub(crate) fn fix_obs_pipewire() -> Result<String, String> {
    run_capture_fix(
        "OBS capture repair",
        gaming_tools::obs_pipewire_fix_command(),
    )
}

/// Opens one of the two well-known game-data folders in the desktop file
/// manager. `key` is validated against `game_folder_path`'s fixed set —
/// never an arbitrary caller-supplied path.
#[tauri::command]
pub(crate) fn open_game_folder(key: String) -> Result<String, String> {
    let raw = gaming_tools::game_folder_path(&key).ok_or_else(|| "unknown folder".to_string())?;
    let home = std::env::var("HOME").map_err(|_| "HOME is not set".to_string())?;
    // Expand a LEADING ~ only: replacen on the first '~' anywhere corrupts
    // paths with a tilde mid-string into bogus locations.
    let expanded = raw
        .strip_prefix("~/")
        .map(|rest| format!("{home}/{rest}"))
        .unwrap_or_else(|| {
            if raw == "~" {
                home.clone()
            } else {
                raw.to_string()
            }
        });
    if !std::path::Path::new(&expanded).exists() {
        return Err(format!("Folder not found yet: {expanded}"));
    }
    kyth_shared::system::process::spawn_detached(Command::new("xdg-open").arg(&expanded))
        .map_err(|err| format!("could not open {expanded}: {err}"))?;
    Ok(format!("Opened {expanded}"))
}

// ---------------------------------------------------------------------
// Overlays / sched-ext / per-game profile builder — page_gaming_tools_perf.py.
// ---------------------------------------------------------------------

#[derive(Serialize)]
pub(crate) struct GamingPerfStatusResponse {
    mangohud_installed: bool,
    gamescope_installed: bool,
    vkbasalt_installed: bool,
}

#[tauri::command]
pub(crate) fn gaming_perf_status() -> GamingPerfStatusResponse {
    GamingPerfStatusResponse {
        mangohud_installed: gaming_perf::mangohud_installed(),
        gamescope_installed: gaming_perf::gamescope_installed(),
        vkbasalt_installed: gaming_perf::vkbasalt_installed(),
    }
}

#[derive(Serialize)]
pub(crate) struct ScxStatusResponse {
    active: bool,
    configured: String,
}

#[tauri::command]
pub(crate) fn scx_status() -> Option<ScxStatusResponse> {
    gaming_perf::scx_status().map(|status| ScxStatusResponse {
        active: status.active,
        configured: status.configured,
    })
}

/// Schedulers installed on this machine (short names: rusty, lavd,
/// bpfland). scx_loader resolves the `scx_` binary, so the list is whatever
/// `kyth-scx list` reports, falling back to `scx_*` binaries on PATH.
#[tauri::command]
pub(crate) fn scx_available() -> Vec<String> {
    use kyth_shared::system::sched_daemon::available_schedulers;
    let run = |argv: &[String], _timeout_secs: u64| -> Option<(i32, String)> {
        let (program, args) = argv.split_first()?;
        let output = Command::new(program).args(args).output().ok()?;
        Some((
            output.status.code().unwrap_or(1),
            String::from_utf8_lossy(&output.stdout).into_owned(),
        ))
    };
    available_schedulers(&run, std::path::Path::new("/usr/bin"))
        .into_iter()
        .map(|name| name.strip_prefix("scx_").unwrap_or(&name).to_string())
        .collect()
}

/// Only schedulers scx_loader can resolve — a fixed set, not an arbitrary
/// scheduler name from the webview. lavd/bpfland fail visibly in the job
/// log when their binaries are not installed.
#[tauri::command]
pub(crate) fn scx_set_scheduler(scheduler: String) -> Result<String, String> {
    if !matches!(scheduler.as_str(), "rusty" | "lavd" | "bpfland" | "stop") {
        return Err("unknown scheduler".to_string());
    }
    let argv = gaming_perf::scx_scheduler_command(&scheduler);
    let job = start_job("scx", &format!("Setting scheduler: {scheduler}…"))?;
    spawn_argv_job(
        job.clone(),
        argv,
        timeout_for(JobTimeoutClass::SchedulerApply),
        |result| match result {
            Ok(output) if output.status.success() => {
                ("complete".to_string(), "sched-ext updated.".to_string())
            }
            Ok(output) => (
                "failed".to_string(),
                failure_detail("sched-ext update", &output),
            ),
            Err(err) => (
                "failed".to_string(),
                format!("Could not start sched-ext update: {err}"),
            ),
        },
    );
    Ok(job)
}

fn valid_appid(appid: &str) -> bool {
    // Steam app ids are short decimal ids. Restrict to digits, max 12, so a
    // crafted id can never smuggle shell metacharacters or option flags.
    // "builder-default" is the goal default the profile builder saves when
    // no app id is entered — previously it failed every such save with
    // "invalid Steam app id" and no path forward.
    appid == "builder-default"
        || (!appid.is_empty()
            && appid.len() <= 12
            && appid.bytes().all(|byte| byte.is_ascii_digit()))
}

#[derive(Serialize)]
pub(crate) struct GameProfileResponse {
    profile: String,
    hdr: bool,
    fps: String,
    prime: bool,
}

#[tauri::command]
pub(crate) fn per_game_profile(appid: String) -> Result<GameProfileResponse, String> {
    if !valid_appid(&appid) {
        return Err("invalid Steam app id".to_string());
    }
    let profile = gaming_per_game::get_profile_for_appid(
        &appid,
        gaming_per_game::per_game_config_path(None::<&str>),
    );
    Ok(GameProfileResponse {
        profile: profile.profile,
        hdr: profile.hdr,
        fps: profile.fps,
        prime: profile.prime,
    })
}

/// The exact Steam launch-options string for a saved profile, so the
/// builder's saves stop being write-only: the user pastes this into
/// Steam → Properties → Launch Options. Nothing is written to Steam's
/// own config — same read-only honesty as the Steam Play check.
#[tauri::command]
pub(crate) fn per_game_launch_options(appid: String) -> Result<String, String> {
    if !valid_appid(&appid) {
        return Err("invalid Steam app id".to_string());
    }
    let saved = gaming_per_game::get_profile_for_appid(
        &appid,
        gaming_per_game::per_game_config_path(None::<&str>),
    );
    let goal = ProfileGoal::parse(&saved.profile).ok_or_else(|| "unknown profile".to_string())?;
    let fps = if saved.fps.is_empty() {
        None
    } else {
        Some(saved.fps.as_str())
    };
    Ok(gaming_perf::build_profile_launch_option(
        goal,
        fps,
        saved.hdr,
        saved.prime,
    ))
}

#[tauri::command]
pub(crate) fn save_per_game_profile(
    appid: String,
    profile: String,
    hdr: bool,
    fps: String,
    prime: bool,
) -> Result<String, String> {
    if !valid_appid(&appid) {
        return Err("invalid Steam app id".to_string());
    }
    if ProfileGoal::parse(&profile).is_none() {
        return Err("unknown profile".to_string());
    }
    gaming_per_game::set_profile_for_appid(
        &appid,
        &profile,
        hdr,
        &fps,
        prime,
        gaming_per_game::per_game_config_path(None::<&str>),
    )
    .map_err(|err| format!("Could not save profile: {err}"))?;
    Ok(format!("Saved {profile} (HDR: {hdr}) for {appid}."))
}
