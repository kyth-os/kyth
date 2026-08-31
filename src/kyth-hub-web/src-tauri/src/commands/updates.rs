use serde::Serialize;

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

#[derive(Serialize)]
pub(crate) struct JustRunResponse {
    pub(crate) launched: bool,
    pub(crate) in_terminal: bool,
}

#[tauri::command]
pub(crate) fn just_run(recipe: String) -> JustRunResponse {
    let launch = kyth_shared::system::just::just_launch(&recipe, &[]);
    JustRunResponse { launched: launch.launched, in_terminal: launch.in_terminal }
}

fn launch_in_terminal(recipe: &str, args: &[&str], then: &str) -> Result<String, String> {
    if !kyth_shared::system::just::terminal_available() {
        return Err(format!(
            "no terminal emulator is installed, so {recipe} cannot ask for its password or show what it did — run `ujust {recipe}` in a terminal instead"
        ));
    }
    if !kyth_shared::system::just::just_launch(recipe, args).launched {
        return Err(format!("could not start {recipe}"));
    }
    Ok(format!("{recipe} is running in its own terminal window — answer the password prompt there, then {then}"))
}

#[tauri::command]
pub(crate) fn bootc_upgrade() -> Result<String, String> {
    if std::path::Path::new("/usr/bin/bootc").exists() || std::path::Path::new("/usr/bin/rpm-ostree").exists() {
        launch_in_terminal("upgrade", &[], "reboot to apply it")
    } else {
        Err("bootc not installed".to_string())
    }
}

#[tauri::command]
pub(crate) fn bootc_rollback() -> Result<String, String> {
    launch_in_terminal("rollback", &[], "reboot into the previous deployment")
}

#[tauri::command]
pub(crate) fn bootc_switch_branch(branch: String) -> Result<String, String> {
    let channel = kyth_shared::system::bootc_policy::switch_channel_arg(&branch)
        .ok_or_else(|| "unknown channel".to_string())?;
    launch_in_terminal("switch-channel", &[channel], &format!("reboot to activate {channel}"))
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
