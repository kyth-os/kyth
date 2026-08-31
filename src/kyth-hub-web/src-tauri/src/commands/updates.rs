use std::collections::HashMap;
use std::process::Command;
use std::sync::{Mutex, OnceLock};
use std::time::Duration;

use serde::Serialize;

static JUST_JOBS: OnceLock<Mutex<HashMap<String, (String, String)>>> = OnceLock::new();

fn just_jobs() -> &'static Mutex<HashMap<String, (String, String)>> {
    JUST_JOBS.get_or_init(|| Mutex::new(HashMap::new()))
}

#[derive(Serialize)]
pub(crate) struct JustRecipeResponse {
    pub(crate) name: String,
    pub(crate) params: String,
    pub(crate) comment: String,
}

#[tauri::command]
pub(crate) fn just_list() -> Vec<JustRecipeResponse> {
    kyth_shared::system::just::just_list()
        .into_iter()
        .map(|recipe| JustRecipeResponse { name: recipe.name, params: recipe.params, comment: recipe.comment })
        .collect()
}

fn just_output_detail(recipe: &str, output: &std::process::Output) -> String {
    let mut text = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr);
    if !stderr.trim().is_empty() {
        if !text.is_empty() { text.push('\n'); }
        text.push_str(&stderr);
    }
    let text = kyth_shared::system::process::strip_ansi(text.trim());
    let detail: String = text.chars().rev().take(800).collect::<String>().chars().rev().collect();
    if !detail.trim().is_empty() {
        return if output.status.success() {
            format!("{recipe} complete — {}", detail.trim())
        } else {
            format!("{recipe} could not be completed — {}", detail.trim())
        };
    }
    if output.status.success() {
        format!("{recipe} complete.")
    } else {
        match output.status.code() {
            Some(code) => format!("{recipe} could not be completed (exit code {code})."),
            None => format!("{recipe} stopped before it could complete."),
        }
    }
}

fn start_just_job(recipe: &str, args: &[&str]) -> Result<String, String> {
    let argv = kyth_shared::system::just::command_for(recipe, args)
        .ok_or_else(|| "recipe or argument is not allowlisted".to_string())?;
    kyth_shared::commands::normalize_command(&argv)
        .map_err(|_| "recipe produced an invalid command".to_string())?;
    let job = format!("just-{}", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_nanos());
    just_jobs().lock().map_err(|_| "just job store is unavailable".to_string())?.insert(job.clone(), ("running".into(), format!("Running {recipe}…")));
    let job_for_thread = job.clone();
    let recipe_for_thread = recipe.to_string();
    std::thread::spawn(move || {
        let mut command = Command::new(&argv[0]);
        command.args(&argv[1..]);
        let inherited = std::env::vars().collect::<std::collections::BTreeMap<_, _>>();
        let sanitized = kyth_shared::commands::environment_for(
            kyth_shared::commands::EnvironmentPolicy::Sanitized,
            &inherited,
        );
        command.env_clear().envs(sanitized);
        kyth_shared::system::just::configure_command(&mut command);
        if std::path::Path::new("/usr/bin/ksshaskpass").exists() {
            command.env("SUDO_ASKPASS", "/usr/bin/ksshaskpass");
        }
        let result = kyth_shared::system::process::run_bounded_command(command, Duration::from_secs(900));
        let (state, detail) = match result {
            Ok(output) => {
                let state = if output.status.success() { "complete" } else { "failed" };
                (state.to_string(), just_output_detail(&recipe_for_thread, &output))
            }
            Err(error) => ("failed".to_string(), format!("Could not start {recipe_for_thread}: {error}")),
        };
        if let Ok(mut store) = just_jobs().lock() {
            store.insert(job_for_thread, (state, detail));
        }
    });
    Ok(job)
}

#[tauri::command]
pub(crate) fn just_run(recipe: String) -> Result<String, String> {
    start_just_job(&recipe, &[])
}

#[tauri::command]
pub(crate) fn just_run_status(job: String) -> crate::InstallStatus {
    let (state, detail) = just_jobs().lock().ok().and_then(|store| store.get(&job).cloned()).unwrap_or(("unknown".into(), "Recipe job not found.".into()));
    crate::InstallStatus { id: job, state, detail }
}

#[tauri::command]
pub(crate) fn bootc_upgrade() -> Result<String, String> {
    if std::path::Path::new("/usr/bin/bootc").exists() || std::path::Path::new("/usr/bin/rpm-ostree").exists() { start_just_job("upgrade", &[]) } else { Err("bootc not installed".to_string()) }
}

#[tauri::command]
pub(crate) fn bootc_rollback() -> Result<String, String> {
    start_just_job("rollback", &[])
}

#[tauri::command]
pub(crate) fn bootc_switch_branch(branch: String) -> Result<String, String> {
    let channel = kyth_shared::system::bootc_policy::switch_channel_arg(&branch)
        .ok_or_else(|| "unknown channel".to_string())?;
    start_just_job("switch-channel", &[channel])
}

#[tauri::command]
pub(crate) fn branch_display_name(tag: Option<String>) -> String {
    kyth_shared::system::bootc_policy::branch_display_name(tag.as_deref())
}

#[derive(Serialize)]
pub(crate) struct UpdateAvailabilityViewResponse {
    pub(crate) card_style: String,
    pub(crate) icon_text: String,
    pub(crate) icon_style: String,
    pub(crate) title: String,
    pub(crate) body: String,
    pub(crate) update_btn_visible: bool,
    pub(crate) restart_btn_visible: bool,
}

#[tauri::command]
pub(crate) fn update_availability_view(
    staged: bool,
    check_state: String,
    flatpak_count: u32,
    check_ts: String,
    check_ts_details: String,
    staged_ts: Option<String>,
) -> UpdateAvailabilityViewResponse {
    let view = kyth_shared::system::bootc_policy::update_availability_view(
        staged, &check_state, flatpak_count, &check_ts, &check_ts_details, staged_ts.as_deref(),
    );
    UpdateAvailabilityViewResponse {
        card_style: view.card_style,
        icon_text: view.icon_text,
        icon_style: view.icon_style,
        title: view.title,
        body: view.body,
        update_btn_visible: view.update_btn_visible,
        restart_btn_visible: view.restart_btn_visible,
    }
}

#[tauri::command]
pub(crate) fn pending_updates_summary() -> std::collections::HashMap<String, String> {
    kyth_shared::system::updates_unified::pending_updates_summary()
}

#[tauri::command]
pub(crate) fn update_status() -> UpdateStatusResponse {
    let status = kyth_shared::system::update_status::check_update_status();
    UpdateStatusResponse {
        booted: status.booted,
        staged: status.staged,
        rollback: status.rollback,
        remote_digest: status.remote_digest,
        blocked_reason: status.blocked_reason,
        retry_cmd: status.retry_cmd,
        check_state: status.check_state,
        detail: status.detail,
    }
}

#[derive(Serialize)]
pub(crate) struct UpdateStatusResponse {
    pub(crate) booted: Option<String>,
    pub(crate) staged: bool,
    pub(crate) rollback: bool,
    pub(crate) remote_digest: Option<String>,
    pub(crate) blocked_reason: Option<String>,
    pub(crate) retry_cmd: Option<String>,
    pub(crate) check_state: String,
    pub(crate) detail: String,
}

#[derive(Serialize)]
pub(crate) struct AvailabilityStatusResponse {
    pub(crate) state: String,
    pub(crate) detail: String,
    pub(crate) flatpak_count: i32,
    pub(crate) flatpak_detail: String,
    pub(crate) staged: bool,
    pub(crate) manifest_raw: String,
    pub(crate) blocked_reason: String,
}

#[tauri::command]
pub(crate) fn collect_availability(branch: Option<String>, use_cached: Option<bool>) -> AvailabilityStatusResponse {
    let status = kyth_shared::system::update_availability::collect_availability(branch.as_deref(), use_cached.unwrap_or(true));
    AvailabilityStatusResponse {
        state: status.state,
        detail: status.detail,
        flatpak_count: status.flatpak_count,
        flatpak_detail: status.flatpak_detail,
        staged: status.staged,
        manifest_raw: status.manifest_raw,
        blocked_reason: status.blocked_reason,
    }
}

#[tauri::command]
pub(crate) fn updater_available() -> bool {
    kyth_shared::system::updater::updater_available()
}
