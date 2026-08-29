// Tauri shell for the Kyth Hub web frontend — the Rust replacement for
// web_shell.py's QWebEngineView window (see that file's module docstring
// for why a native shell exists at all: same single-instance + --page
// deep-link contract the current PySide6 Hub has, just hosting the React
// build instead of a QWidget tree).
//
// The four bridge commands below used to shell out to backend/*.py
// scripts (see git history if you need the old ones) — they now call
// straight into the kyth-shared crate (../../kyth-shared-rs), no
// subprocess, no JSON-over-stdout round trip. That crate is the first
// slice of kyth_shared (the ~200-module Python library) ported to Rust —
// see its MIGRATION.md for scope. Everything kyth_shared does that isn't
// in that crate yet — most of it — stays Python for now; nothing here
// assumes the rest gets ported on any particular timeline.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;
use std::process::{Command, Stdio};
use std::sync::{Mutex, OnceLock};

use serde::Serialize;
use tauri::{Emitter, Manager};

/// Page-key -> nothing here; route mapping now lives on the TS side
/// (src/deepLink.ts) since the router already owns that table — this
/// process only extracts the raw `--page <key>` argument and forwards it
/// unchanged, whether that's at first launch (via `take_pending_page`) or
/// on a later single-instance activation (via the "navigate" event).
struct PendingPage(Mutex<Option<String>>);

static APP_INSTALLS: OnceLock<Mutex<HashMap<String, (String, String)>>> = OnceLock::new();
fn app_installs() -> &'static Mutex<HashMap<String, (String, String)>> { APP_INSTALLS.get_or_init(|| Mutex::new(HashMap::new())) }
static GUARDIAN_CHECKS: OnceLock<Mutex<HashMap<String, (String, String)>>> = OnceLock::new();
fn guardian_checks() -> &'static Mutex<HashMap<String, (String, String)>> { GUARDIAN_CHECKS.get_or_init(|| Mutex::new(HashMap::new())) }
static PRIVILEGED_JOBS: OnceLock<Mutex<HashMap<String, (String, String)>>> = OnceLock::new();
fn privileged_jobs() -> &'static Mutex<HashMap<String, (String, String)>> { PRIVILEGED_JOBS.get_or_init(|| Mutex::new(HashMap::new())) }
static JUST_JOBS: OnceLock<Mutex<HashMap<String, (String, String)>>> = OnceLock::new();
fn just_jobs() -> &'static Mutex<HashMap<String, (String, String)>> { JUST_JOBS.get_or_init(|| Mutex::new(HashMap::new())) }

fn extract_page_arg<S: AsRef<str>>(argv: &[S]) -> Option<String> {
    argv.iter()
        .position(|a| a.as_ref() == "--page")
        .and_then(|i| argv.get(i + 1))
        .map(|s| s.as_ref().to_string())
}

/// Same response shape the retired probe_bridge.py printed — the frontend
/// (services/liveData.ts) already deserializes this, unchanged.
#[derive(Serialize)]
struct ProbeResponse {
    key: String,
    data: Option<serde_json::Value>,
    error: Option<String>,
}

/// Reads one disk-backed probe section (see kyth_shared's DISK_TTL for
/// valid keys). Read-only, bounded by whatever read_section does — no
/// fresh system probing happens here.
#[tauri::command]
fn probe_backend(section: String) -> ProbeResponse {
    let data = kyth_shared::system::probe::read_section(&section);
    ProbeResponse { key: section, data, error: None }
}

#[derive(Serialize)]
struct GuardianPendingResponse {
    // recipe_id is what guardian_execute_recipe gates on, so it has to
    // reach the frontend for a "run this fix" button to exist at all.
    recipe_id: String,
    title: String,
    detail: String,
    risk: String,
}

#[derive(Serialize)]
struct GuardianHistoryResponse {
    timestamp: f64,
    title: String,
    detail: String,
    action: String,
    verified: Option<bool>,
}

#[derive(Serialize)]
struct GuardianSnapshotResponse {
    pending_count: usize,
    pending: Vec<GuardianPendingResponse>,
    history: Vec<GuardianHistoryResponse>,
}

/// Guardian's pending-recommendation list + recent history, from disk —
/// deliberately does NOT trigger a live symptom probe (see
/// kyth_shared::guardian's module docs for why that boundary matters).
#[tauri::command]
fn guardian_snapshot() -> GuardianSnapshotResponse {
    let state = kyth_shared::guardian::load_state();
    let pending = kyth_shared::guardian::pending_recommendations(&state);
    let pending_response = pending
        .iter()
        .map(|p| GuardianPendingResponse {
            recipe_id: p.recipe_id.clone(),
            title: kyth_shared::guardian::recipe_title(&p.recipe_id),
            detail: p.detail.clone(),
            risk: kyth_shared::guardian::recipe_risk(&p.recipe_id),
        })
        .collect();

    let history_response = kyth_shared::guardian::recent_history(&state, 8)
        .into_iter()
        .map(|item| GuardianHistoryResponse {
            timestamp: item.timestamp,
            title: item
                .recipe_id
                .as_deref()
                .map(kyth_shared::guardian::recipe_title)
                .unwrap_or_else(|| "Guardian".to_string()),
            detail: item.detail,
            action: item.action,
            verified: item.verified,
        })
        .collect();

    GuardianSnapshotResponse { pending_count: pending.len(), pending: pending_response, history: history_response }
}

/// Ask the existing Python Guardian service for a fresh check, then let the
/// frontend re-read the disk-backed snapshot.  The Rust shell does not port
/// the live probe sweep; Python remains the authority for that behavior.
#[tauri::command]
fn guardian_check(investigate: bool) -> Result<String, String> {
    if !std::path::Path::new("/usr/bin/kyth-guardian").exists() { return Err("Guardian service is not installed".to_string()); }
    let job = format!("guardian-{}", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_nanos());
    guardian_checks().lock().unwrap().insert(job.clone(), ("running".into(), "Guardian check is running…".into()));
    let job_for_thread = job.clone();
    std::thread::spawn(move || {
        let action = if investigate { "investigate" } else { "check" };
        let result = std::process::Command::new("/usr/bin/kyth-guardian").args(["--json", action]).output();
        let (state, detail) = match result {
            Ok(output) if output.status.success() => ("complete", "Guardian check complete.".to_string()),
            Ok(output) => { let detail = String::from_utf8_lossy(&output.stderr).trim().chars().take(400).collect(); ("failed", detail) }
            Err(err) => ("failed", format!("Could not start Guardian: {err}")),
        };
        guardian_checks().lock().unwrap().insert(job_for_thread, (state.into(), detail));
    });
    Ok(job)
}

#[tauri::command]
fn guardian_check_status(job: String) -> InstallStatus {
    let (state, detail) = guardian_checks().lock().unwrap().get(&job).cloned().unwrap_or(("unknown".into(), "Guardian job not found.".into()));
    InstallStatus { id: job, state, detail }
}

#[tauri::command]
fn guardian_control(action: String) -> Result<String, String> {
    let args: &[&str] = match action.as_str() {
        "enable" => &["enable"],
        "disable" => &["disable"],
        "autofix-on" => &["auto-fix", "on"],
        "autofix-off" => &["auto-fix", "off"],
        _ => return Err("Guardian control is not allowlisted".to_string()),
    };
    let job = format!("guardian-control-{}", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_nanos());
    guardian_checks().lock().unwrap().insert(job.clone(), ("running".into(), format!("Running Guardian {action}…")));
    let job_for_thread = job.clone();
    std::thread::spawn(move || {
        let result = std::process::Command::new("/usr/bin/kyth-guardian").args(args).output();
        let (state, detail) = match result {
            Ok(output) if output.status.success() => ("complete", String::from_utf8_lossy(&output.stdout).trim().to_string()),
            Ok(output) => ("failed", String::from_utf8_lossy(&output.stderr).trim().chars().take(400).collect()),
            Err(err) => ("failed", format!("Could not start Guardian: {err}")),
        };
        guardian_checks().lock().unwrap().insert(job_for_thread, (state.into(), if detail.is_empty() { "Guardian control complete.".into() } else { detail }));
    });
    Ok(job)
}

#[derive(Serialize)]
struct HardwareResponse {
    gpu_line: Option<String>,
}

/// Raw first `lspci -nn` GPU line, if any.
#[tauri::command]
fn hardware_snapshot() -> HardwareResponse {
    HardwareResponse { gpu_line: kyth_shared::system::gpu::lspci_gpu_lines().into_iter().next() }
}

#[derive(Serialize)]
struct StorageResponse {
    free_bytes: Option<u64>,
    total_bytes: Option<u64>,
}

/// Free/total bytes on the same filesystem Guardian's own storage check
/// looks at.
#[tauri::command]
fn storage_snapshot() -> StorageResponse {
    match kyth_shared::system::storage::primary_disk_usage() {
        Some(usage) => StorageResponse { free_bytes: Some(usage.free_bytes), total_bytes: Some(usage.total_bytes) },
        None => StorageResponse { free_bytes: None, total_bytes: None },
    }
}

#[derive(Serialize)]
struct JustRecipeResponse {
    name: String,
    /// Parameters as `just --list` prints them. The section renders a row
    /// with parameters as text rather than a button, because a launch
    /// passes no arguments — so this field has to cross the bridge. It did
    /// not, which left `switch-kernel flavor="fedora"` a one-click switch
    /// off the CachyOS default under a label that only said its name.
    params: String,
    comment: String,
}

/// `just --list` recipes, parsed like `page_just.py`. The whole list
/// crosses the bridge (the shipped justfile has ~200); the frontend filters
/// it and caps its own display at 30 like the Qt page did.
#[tauri::command]
fn just_list() -> Vec<JustRecipeResponse> {
    kyth_shared::system::just::just_list()
        .into_iter()
        .map(|r| JustRecipeResponse { name: r.name, params: r.params, comment: r.comment })
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

/// Start a validated `just` recipe in the background and retain a concise
/// captured result for the Hub. Authentication uses KDE's graphical askpass
/// helper when it is installed, so sudo does not need an interactive tty.
fn start_just_job(recipe: &str, args: &[&str]) -> Result<String, String> {
    let argv = kyth_shared::system::just::command_for(recipe, args)
        .ok_or_else(|| "recipe or argument is not allowlisted".to_string())?;
    let job = format!("just-{}", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_nanos());
    just_jobs().lock().unwrap().insert(job.clone(), ("running".into(), format!("Running {recipe}…")));
    let job_for_thread = job.clone();
    let recipe_for_thread = recipe.to_string();
    std::thread::spawn(move || {
        let mut command = Command::new(&argv[0]);
        command.args(&argv[1..]);
        kyth_shared::system::just::configure_command(&mut command);
        if std::path::Path::new("/usr/bin/ksshaskpass").exists() {
            command.env("SUDO_ASKPASS", "/usr/bin/ksshaskpass");
        }
        let result = command.stdout(Stdio::piped()).stderr(Stdio::piped()).output();
        let (state, detail) = match result {
            Ok(output) => {
                let state = if output.status.success() { "complete" } else { "failed" };
                (state.to_string(), just_output_detail(&recipe_for_thread, &output))
            }
            Err(err) => ("failed".to_string(), format!("Could not start {recipe_for_thread}: {err}")),
        };
        just_jobs().lock().unwrap().insert(job_for_thread, (state, detail));
    });
    Ok(job)
}

/// Start a no-argument recipe. The process is owned by the Hub and its
/// progress/result is returned through `just_run_status`.
#[tauri::command]
fn just_run(recipe: String) -> Result<String, String> {
    start_just_job(&recipe, &[])
}

#[tauri::command]
fn just_run_status(job: String) -> InstallStatus {
    let (state, detail) = just_jobs().lock().unwrap().get(&job).cloned().unwrap_or(("unknown".into(), "Recipe job not found.".into()));
    InstallStatus { id: job, state, detail }
}

/// Phase 2 mutating: bootc upgrade/rollback/switch — polkit-guarded via pkexec/systemd-run allowlist.
#[tauri::command]
fn bootc_upgrade() -> Result<String, String> {
    sanitize_upgrade()?;
    start_just_job("upgrade", &[])
}
#[tauri::command]
fn bootc_rollback() -> Result<String, String> {
    start_just_job("rollback", &[])
}
#[tauri::command]
fn bootc_switch_branch(branch: String) -> Result<String, String> {
    // Allowlist, then spawn the same `just switch-channel` recipe a user
    // would run by hand — the recipe stages the switch via kyth-bootc-guard
    // and does its own sudo prompt, so this matches how bootc_upgrade and
    // bootc_rollback delegate rather than touching bootc directly.
    //
    // switch_channel_arg returns a fixed literal, never the caller's
    // string, so nothing user-controlled reaches the argv.
    let channel = kyth_shared::system::bootc_policy::switch_channel_arg(&branch)
        .ok_or_else(|| "unknown channel".to_string())?;
    // Through the validated just runner rather than a raw Command, so this
    // gets the justfile resolution `ujust` performs without opening a
    // terminal window.
    start_just_job("switch-channel", &[channel])
}
fn sanitize_upgrade() -> Result<(), String> {
    // allowlist: only expose when bootc binary present; polkit prompt happens in the spawned just recipe (pkexec inside recipe)
    if std::path::Path::new("/usr/bin/bootc").exists() || std::path::Path::new("/usr/bin/rpm-ostree").exists() { Ok(()) } else { Err("bootc not installed".to_string()) }
}
/// Phase 2: guardian execute_recipe (Repair/Diagnostics mutating)
#[tauri::command]
fn guardian_execute_recipe(recipe_id: String) -> Result<String, String> {
    let state = kyth_shared::guardian::load_state();
    if !kyth_shared::guardian::is_pending_recipe(&state, &recipe_id) { return Err("recipe not pending".to_string()); }
    // Guardian ids are dotted (`audio.restart`) and are not just recipes —
    // handing them to `just_run` ran nothing and reported "launched" for
    // every one of them, advisory notifications included. `execute_recipe`
    // carries guardian.py's own eligibility gate and runs the recipe's argv.
    let detail = kyth_shared::guardian::execute_recipe(&recipe_id)?;
    Ok(format!("{}: {detail}", kyth_shared::guardian::recipe_title(&recipe_id)))
}

#[tauri::command]
fn branch_display_name(tag: Option<String>) -> String {
    kyth_shared::system::bootc_policy::branch_display_name(tag.as_deref())
}

#[derive(Serialize)]
struct UpdateAvailabilityViewResponse {
    card_style: String,
    icon_text: String,
    icon_style: String,
    title: String,
    body: String,
    update_btn_visible: bool,
    restart_btn_visible: bool,
}

#[tauri::command]
fn update_availability_view(
    staged: bool,
    check_state: String,
    flatpak_count: u32,
    check_ts: String,
    check_ts_details: String,
    staged_ts: Option<String>,
) -> UpdateAvailabilityViewResponse {
    let v = kyth_shared::system::bootc_policy::update_availability_view(
        staged,
        &check_state,
        flatpak_count,
        &check_ts,
        &check_ts_details,
        staged_ts.as_deref(),
    );
    UpdateAvailabilityViewResponse {
        card_style: v.card_style,
        icon_text: v.icon_text,
        icon_style: v.icon_style,
        title: v.title,
        body: v.body,
        update_btn_visible: v.update_btn_visible,
        restart_btn_visible: v.restart_btn_visible,
    }
}

#[derive(serde::Serialize)]
struct MokStatusResponse {
    sb_state: String,
    enrolled: String,
}

/// Live Secure Boot + MOK enrollment (N40) — runs mokutil (5s each).
#[tauri::command]
fn mok_status() -> MokStatusResponse {
    let s = kyth_shared::system::mok_verify::mok_status();
    MokStatusResponse { sb_state: s.sb_state, enrolled: s.enrolled }
}

#[derive(serde::Serialize)]
struct FontsReadyResponse { ready: bool, detail: String, }
#[tauri::command]
fn fonts_ready() -> FontsReadyResponse {
    let (ready, detail) = kyth_shared::system::fonts_ready::fonts_ready();
    FontsReadyResponse { ready, detail }
}

#[tauri::command]
fn current_user_name() -> String { kyth_shared::system::account::current_user_display_name() }

#[tauri::command]
fn mesa_version() -> String { kyth_shared::system::mesa_version::mesa_version() }
#[derive(serde::Serialize)]
struct MesaOverlayResponse { ok: bool, detail: String, }
#[tauri::command]
fn mesa_overlay_dry_run() -> MesaOverlayResponse {
    let (ok, detail) = kyth_shared::system::mesa_version::mesa_overlay_dry_run();
    MesaOverlayResponse { ok, detail }
}

#[derive(serde::Serialize)]
struct SmbBrowseResponse { ok: bool, detail: String, }
#[tauri::command]
fn smb_browse(host: Option<String>) -> SmbBrowseResponse {
    let (ok, detail) = kyth_shared::system::smb::smb_browse_dry_run(host.as_deref());
    SmbBrowseResponse { ok, detail }
}
#[tauri::command]
fn smb_mount_command(share: String) -> Vec<String> { kyth_shared::system::smb::smb_mount_command(&share) }

#[derive(serde::Serialize)]
struct MemoryPressureResponse { status: String, detail: String, }
#[tauri::command]
fn memory_pressure() -> MemoryPressureResponse {
    let (status, detail) = kyth_shared::system::memory_pressure::memory_pressure_status();
    MemoryPressureResponse { status, detail }
}
#[tauri::command]
fn snapshot_count() -> usize { kyth_shared::system::snapshot::snapshot_count() }

#[tauri::command]
fn gaming_slice_command(argv: Vec<String>, use_user: Option<bool>) -> Vec<String> {
    kyth_shared::system::gaming_slice::gaming_slice_command(&argv, use_user)
}
#[tauri::command]
fn is_gaming_slice_available() -> bool { kyth_shared::system::gaming_slice::is_gaming_slice_available() }

#[derive(serde::Serialize)]
struct CloudOauthResponse { ok: bool, detail: String, }
#[tauri::command]
fn cloud_oauth_status() -> CloudOauthResponse { let (ok, detail)=kyth_shared::system::cloud_oauth::cloud_oauth_status(); CloudOauthResponse{ok, detail} }
#[tauri::command]
fn rclone_oauth_command(remote: String) -> Vec<String> { kyth_shared::system::cloud_oauth::rclone_oauth_command(&remote) }
#[tauri::command]
fn ipp_discover() -> Vec<String> { kyth_shared::system::printing::ipp_discover() }
#[tauri::command]
fn printer_setup_command() -> Vec<String> { kyth_shared::system::printing::printer_setup_command() }

#[derive(serde::Serialize)]
struct BtrfsHealthResponse { status: String, detail: String, }
#[tauri::command]
fn btrfs_health() -> BtrfsHealthResponse { let (status, detail)=kyth_shared::system::btrfs_status::btrfs_health_summary(); BtrfsHealthResponse{status, detail} }
#[tauri::command]
fn loaded_kernel_modules() -> Vec<String> { kyth_shared::system::drivers::get_loaded_kernel_modules().into_iter().collect() }
#[tauri::command]
fn pci_devices_by_class(class: String) -> Vec<String> { kyth_shared::system::drivers::get_pci_devices_by_class(&class) }

#[tauri::command]
fn controllers_detect() -> ControllersDetectResponse {
    let d = kyth_shared::system::controllers::detect_controllers();
    ControllersDetectResponse {
        usb_controllers: d.usb_controllers,
        input_nodes: d.input_nodes,
        xone_dongle: d.xone_dongle,
        xone_loaded: d.xone_loaded,
        xpadneo_loaded: d.xpadneo_loaded,
        hid_ps_loaded: d.hid_ps_loaded,
        dualsense_found: d.dualsense_found,
    }
}
#[derive(serde::Serialize)]
struct ControllersDetectResponse {
    usb_controllers: Vec<(String,String)>,
    input_nodes: Vec<String>,
    xone_dongle: bool,
    xone_loaded: bool,
    xpadneo_loaded: bool,
    hid_ps_loaded: bool,
    dualsense_found: bool,
}

#[tauri::command]
fn hardware_view_summary() -> Option<HardwareViewSummaryResponse> {
    kyth_shared::system::hardware_view::get_hardware_view_summary().map(|v| HardwareViewSummaryResponse { has_nvidia: v.has_nvidia, is_hybrid: v.is_hybrid, capabilities: v.capabilities })
}
#[derive(serde::Serialize)]
struct HardwareViewSummaryResponse { has_nvidia: bool, is_hybrid: bool, capabilities: Vec<String>, }

#[tauri::command]
fn network_identity() -> NetworkIdentityResponse {
    let n = kyth_shared::system::network_identity::get_network_identity();
    NetworkIdentityResponse { vpn_connected: n.vpn_connected, vpn_name: n.vpn_name, smb_mounts: n.smb_mounts, cloud_providers: n.cloud_providers, detail: n.detail }
}
#[derive(serde::Serialize)]
struct NetworkIdentityResponse { vpn_connected: bool, vpn_name: String, smb_mounts: i32, cloud_providers: Vec<String>, detail: String, }

#[tauri::command]
fn pending_updates_summary() -> std::collections::HashMap<String,String> { kyth_shared::system::updates_unified::pending_updates_summary() }
#[tauri::command]
fn rollback_command() -> Vec<String> { kyth_shared::system::updates_unified::rollback_command() }

#[tauri::command]
fn available_audio_presets() -> Vec<String> { kyth_shared::system::pipewire::available_audio_presets() }
#[derive(serde::Serialize)]
struct PipewireApplyResponse { ok: bool, detail: String, }
#[tauri::command]
fn apply_pipewire_quantum(preset: String, dry_run: bool) -> PipewireApplyResponse { let (ok, detail)=kyth_shared::system::pipewire::apply_pipewire_quantum(&preset, dry_run); PipewireApplyResponse{ok, detail} }

#[tauri::command]
fn deployment_history() -> Vec<DeploymentInfoResponse> {
    kyth_shared::system::deployment_history::deployment_history().into_iter().map(|d| DeploymentInfoResponse { section: d.section, label: d.label, available: d.available, reference: d.reference, branch: d.branch, timestamp: d.timestamp, digest: d.digest, short_digest: d.short_digest, status_text: d.status_text }).collect()
}
#[derive(serde::Serialize)]
struct DeploymentInfoResponse { section: String, label: String, available: bool, reference: Option<String>, branch: Option<String>, timestamp: Option<String>, digest: Option<String>, short_digest: Option<String>, status_text: String, }

#[derive(serde::Serialize)]
struct RecoveryStatusResponse { has_staged: bool, has_rollback: bool, quarantined_digest: String, quarantine_detail: String, watcher_staged: bool, clear_quarantine_cmd: String, banner: String, }
#[tauri::command]
fn recovery_status() -> RecoveryStatusResponse {
    let s = kyth_shared::system::recovery_status::get_recovery_status();
    let banner = kyth_shared::system::recovery_status::recovery_banner(&s);
    RecoveryStatusResponse { has_staged: s.has_staged, has_rollback: s.has_rollback, quarantined_digest: s.quarantined_digest, quarantine_detail: s.quarantine_detail, watcher_staged: s.watcher_staged, clear_quarantine_cmd: s.clear_quarantine_cmd, banner }
}

#[tauri::command]
fn update_status() -> UpdateStatusResponse {
    let s = kyth_shared::system::update_status::check_update_status();
    UpdateStatusResponse { booted: s.booted, staged: s.staged, rollback: s.rollback, remote_digest: s.remote_digest, blocked_reason: s.blocked_reason, retry_cmd: s.retry_cmd, check_state: s.check_state, detail: s.detail }
}
#[derive(serde::Serialize)]
struct UpdateStatusResponse { booted: Option<String>, staged: bool, rollback: bool, remote_digest: Option<String>, blocked_reason: Option<String>, retry_cmd: Option<String>, check_state: String, detail: String, }

#[tauri::command]
fn gaming_library() -> Vec<kyth_shared::system::gaming_library::LauncherEntry> {
    kyth_shared::system::gaming_library::gaming_library_scan()
}

#[tauri::command]
fn starter_packs() -> Vec<kyth_shared::system::software_catalog::StarterPack> {
    kyth_shared::system::software_catalog::starter_packs()
}

#[tauri::command]
fn familiar_apps() -> Vec<kyth_shared::system::software_catalog::FamiliarApp> {
    kyth_shared::system::software_catalog::familiar_apps()
}

#[tauri::command]
fn appstream_search(query: String) -> Vec<kyth_shared::system::software_catalog::AppStreamApp> {
    kyth_shared::system::software_catalog::appstream_search(&query)
}

#[tauri::command]
fn appimage_list() -> Vec<kyth_shared::system::software_catalog::AppImageEntry> {
    kyth_shared::system::software_catalog::appimages()
}

#[tauri::command]
fn installed_flatpaks() -> Vec<kyth_shared::system::software_catalog::InstalledFlatpak> {
    kyth_shared::system::software_catalog::installed_flatpaks()
}

#[tauri::command]
fn uninstall_flatpak(app_id: String) -> Result<String, String> {
    if app_id.is_empty() || !app_id.chars().all(|c| c.is_ascii_alphanumeric() || c == '.') {
        return Err("invalid Flatpak application id".to_string());
    }
    let scope = kyth_shared::system::software_catalog::installed_flatpaks().into_iter().find(|app| app.id == app_id).map(|app| app.scope).ok_or_else(|| "that Flatpak is not installed".to_string())?;
    let job = format!("flatpak-uninstall-{}", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_nanos());
    app_installs().lock().unwrap().insert(job.clone(), ("running".into(), format!("Uninstalling {app_id}…")));
    let job_for_thread = job.clone();
    std::thread::spawn(move || {
        let result: Result<(bool, String), String> = if scope == "system" {
            privileged_flatpak_uninstall(&app_id).map(|detail| (true, detail))
        } else {
            std::process::Command::new("flatpak").args(["uninstall", "--user", "-y", &app_id]).output().map(|output| {
                if output.status.success() { (true, format!("Uninstalled {app_id}.")) }
                else { (false, String::from_utf8_lossy(&output.stderr).trim().chars().take(400).collect()) }
            }).map_err(|err| err.to_string())
        };
        let (state, detail) = match result {
            Ok((true, detail)) => ("complete", detail),
            Ok((false, detail)) => ("failed", detail),
            Err(err) => ("failed", format!("Could not uninstall Flatpak: {err}")),
        };
        app_installs().lock().unwrap().insert(job_for_thread, (state.into(), detail));
    });
    Ok(job)
}

fn privileged_flatpak_uninstall(app_id: &str) -> Result<String, String> {
    let mut stream = UnixStream::connect("/run/kyth/privileged.sock").map_err(|_| "privileged service is unavailable".to_string())?;
    stream.set_read_timeout(Some(std::time::Duration::from_secs(610))).ok();
    stream.write_all(format!("{{\"operation\":\"flatpak_uninstall\",\"app_id\":\"{app_id}\"}}\n").as_bytes()).map_err(|err| format!("could not contact privileged service: {err}"))?;
    let mut response = String::new();
    BufReader::new(stream).read_line(&mut response).map_err(|err| format!("could not read privileged service: {err}"))?;
    let value: serde_json::Value = serde_json::from_str(&response).map_err(|err| format!("invalid privileged service response: {err}"))?;
    if value.get("ok").and_then(serde_json::Value::as_bool).unwrap_or(false) { Ok(value.get("detail").and_then(serde_json::Value::as_str).unwrap_or("Uninstall complete.").to_string()) } else { Err(value.get("detail").and_then(serde_json::Value::as_str).unwrap_or("privileged uninstall failed").to_string()) }
}

#[tauri::command]
fn privileged_action(operation: String, payload: serde_json::Value) -> Result<String, String> {
    let request = match operation.as_str() {
        "firmware_update" | "nvidia_install" | "windows_verify" | "secureboot_enroll" => serde_json::json!({"operation": operation}),
        "kernel_switch" => {
            let flavor = payload.get("flavor").and_then(serde_json::Value::as_str).ok_or_else(|| "kernel flavor is required".to_string())?;
            if !matches!(flavor, "fedora" | "cachy") { return Err("kernel flavor must be fedora or cachy".to_string()); }
            serde_json::json!({"operation": "kernel_switch", "flavor": flavor})
        }
        "bitlocker_unlock" => {
            let device = payload.get("device").and_then(serde_json::Value::as_str).ok_or_else(|| "block device is required".to_string())?;
            let key = payload.get("key").and_then(serde_json::Value::as_str).ok_or_else(|| "BitLocker key is required".to_string())?;
            serde_json::json!({"operation": "bitlocker_unlock", "device": device, "key": key})
        }
        _ => return Err("privileged operation is not allowlisted".to_string()),
    };
    let job = format!("privileged-{}", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_nanos());
    privileged_jobs().lock().unwrap().insert(job.clone(), ("running".into(), format!("Running {operation}…")));
    let job_for_thread = job.clone();
    std::thread::spawn(move || {
        let result = send_privileged_request(request);
        let (state, detail) = match result {
            Ok(detail) => ("complete", detail),
            Err(detail) => ("failed", detail),
        };
        privileged_jobs().lock().unwrap().insert(job_for_thread, (state.into(), detail));
    });
    Ok(job)
}

fn send_privileged_request(request: serde_json::Value) -> Result<String, String> {
    let mut stream = UnixStream::connect("/run/kyth/privileged.sock").map_err(|_| "privileged service is unavailable".to_string())?;
    stream.set_read_timeout(Some(std::time::Duration::from_secs(910))).ok();
    stream.write_all(format!("{}\n", request).as_bytes()).map_err(|err| format!("could not contact privileged service: {err}"))?;
    let mut response = String::new();
    BufReader::new(stream).read_line(&mut response).map_err(|err| format!("could not read privileged service: {err}"))?;
    let value: serde_json::Value = serde_json::from_str(&response).map_err(|err| format!("invalid privileged service response: {err}"))?;
    if value.get("ok").and_then(serde_json::Value::as_bool).unwrap_or(false) { Ok(value.get("detail").and_then(serde_json::Value::as_str).unwrap_or("Operation complete.").to_string()) } else { Err(value.get("detail").and_then(serde_json::Value::as_str).unwrap_or("privileged operation failed").to_string()) }
}

#[tauri::command]
fn privileged_action_status(job: String) -> InstallStatus {
    let (state, detail) = privileged_jobs().lock().unwrap().get(&job).cloned().unwrap_or(("unknown".into(), "Privileged job not found.".into()));
    InstallStatus { id: job, state, detail }
}

#[tauri::command]
fn make_appimage_executable(path: String) -> Result<String, String> {
    kyth_shared::system::software_catalog::make_appimage_executable(&path)
}

#[tauri::command]
fn import_appimage(path: String) -> Result<String, String> {
    kyth_shared::system::software_catalog::import_appimage(&path)
}

#[tauri::command]
fn launch_appimage(path: String) -> Result<String, String> {
    let allowed = kyth_shared::system::software_catalog::appimages().into_iter().any(|app| app.path == path && app.executable);
    if !allowed { return Err("AppImage is not a discovered executable in an allowed user directory".to_string()); }
    std::process::Command::new(&path).spawn().map(|_| "AppImage launched.".to_string()).map_err(|err| format!("could not launch AppImage: {err}"))
}

#[derive(serde::Serialize)]
struct InstallStatus {
    id: String,
    state: String,
    detail: String,
}

#[tauri::command]
fn install_flatpak(app_id: String) -> Result<String, String> {
    if app_id.is_empty() || app_id.len() > 200 || !app_id.chars().all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '-' | '_')) {
        return Err("invalid Flatpak application id".to_string());
    }
    let job = format!("flatpak-{}", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_nanos());
    app_installs().lock().unwrap().insert(job.clone(), ("running".into(), format!("Installing {app_id}…")));
    let job_for_thread = job.clone();
    std::thread::spawn(move || {
        let result = std::process::Command::new("flatpak").args(["install", "--user", "-y", "flathub", &app_id]).output();
        let (state, detail) = match result {
            Ok(output) if output.status.success() => ("complete", "Installation complete.".to_string()),
            Ok(output) => ("failed", String::from_utf8_lossy(&output.stderr).trim().chars().take(400).collect()),
            Err(err) => ("failed", format!("Could not start Flatpak: {err}")),
        };
        app_installs().lock().unwrap().insert(job_for_thread, (state.into(), detail));
    });
    Ok(job)
}

#[tauri::command]
fn install_status(job: String) -> InstallStatus {
    let (state, detail) = app_installs().lock().unwrap().get(&job).cloned().unwrap_or(("unknown".into(), "Installation job not found.".into()));
    InstallStatus { id: job, state, detail }
}

#[tauri::command]
fn protondb_lookup_many(app_ids: Vec<String>) -> Vec<kyth_shared::system::gaming_compat::ProtonDbResult> {
    kyth_shared::system::gaming_compat::protondb_lookup_many(&app_ids)
}

#[tauri::command]
fn anti_cheat_table() -> Vec<kyth_shared::system::gaming_compat::AntiCheatEntry> {
    kyth_shared::system::gaming_compat::anti_cheat_table()
}

#[tauri::command]
fn telemetry_recent(limit: Option<u32>) -> Vec<kyth_shared::system::telemetry::SessionRow> {
    kyth_shared::system::telemetry::recent_sessions(limit.unwrap_or(15) as usize)
}

#[tauri::command]
fn is_live_session() -> bool { kyth_shared::system::process::is_live_session() }
#[tauri::command]
fn strip_ansi(text: String) -> String { kyth_shared::system::process::strip_ansi(&text) }
#[tauri::command]
fn disk_write_bytes() -> u64 { kyth_shared::system::process::get_disk_write_bytes() }

#[tauri::command]
fn firmware_updates_count() -> i32 { kyth_shared::system::firmware::check_firmware_updates(20) }
#[tauri::command]
fn firmware_devices_command() -> Vec<String> { kyth_shared::system::firmware::firmware_devices_command() }

#[tauri::command]
fn plasma_presets() -> Vec<String> { kyth_shared::system::plasma_hdr::available_presets() }
#[derive(serde::Serialize)]
struct PlasmaApplyResponse { ok: bool, detail: String, }
#[tauri::command]
fn apply_plasma_preset(preset: String, dry_run: bool) -> PlasmaApplyResponse { let (ok, detail)=kyth_shared::system::plasma_hdr::apply_preset(&preset, dry_run); PlasmaApplyResponse{ok, detail} }

#[tauri::command]
fn amd64_manifest_entry(manifest: serde_json::Value) -> Option<serde_json::Value> { kyth_shared::system::registry::amd64_manifest_entry(&manifest) }

#[derive(serde::Serialize)]
struct AvailabilityStatusResponse { state: String, detail: String, flatpak_count: i32, flatpak_detail: String, staged: bool, manifest_raw: String, blocked_reason: String, }
#[tauri::command]
fn collect_availability(branch: Option<String>, use_cached: Option<bool>) -> AvailabilityStatusResponse {
    let s = kyth_shared::system::update_availability::collect_availability(branch.as_deref(), use_cached.unwrap_or(true));
    AvailabilityStatusResponse { state: s.state, detail: s.detail, flatpak_count: s.flatpak_count, flatpak_detail: s.flatpak_detail, staged: s.staged, manifest_raw: s.manifest_raw, blocked_reason: s.blocked_reason }
}

#[tauri::command]
fn ntfs_devices() -> Vec<serde_json::Value> { kyth_shared::system::drives::get_ntfs_devices() }

#[tauri::command]
fn boot_runtime_checks() -> Vec<BootRuntimeCheckResponse> { kyth_shared::system::boot_runtime::boot_runtime_checks().into_iter().map(|c| BootRuntimeCheckResponse{name:c.name, passed:c.passed, detail:c.detail}).collect() }
#[derive(serde::Serialize)]
struct BootRuntimeCheckResponse { name: String, passed: bool, detail: String, }
#[tauri::command]
fn desktop_stack_checks() -> Vec<String> { kyth_shared::system::desktop_stack::desktop_stack_checks() }
#[tauri::command]
fn updater_available() -> bool { kyth_shared::system::updater::updater_available() }

/// Opens a prefilled `kyth-os/kyth` issue in the user's browser — the
/// Feedback section's actual send path. Host and repo are fixed here
/// rather than passed in; only the title and body travel from the
/// frontend, and both are percent-encoded before they reach `xdg-open`,
/// so this can't be pointed at an arbitrary URL.
#[tauri::command]
fn open_feedback_issue(title: String, body: String) -> Result<String, String> {
    // Keep the public-report boundary safe even if a future caller bypasses
    // the retired Python Feedback page's scrub step.
    let body = kyth_shared::diagnostics_scrub::scrub_logs(&body);
    let url = format!(
        "https://github.com/kyth-os/kyth/issues/new?title={}&body={}",
        percent_encode(&title),
        percent_encode(&body)
    );
    std::process::Command::new("xdg-open")
        .arg(&url)
        .spawn()
        .map_err(|err| format!("could not open browser: {err}"))?;
    Ok("Opened a prefilled issue in your browser.".to_string())
}

/// Minimal RFC 3986 unreserved-set encoder — enough for a query string,
/// and not worth a `percent-encoding` dependency for one call site.
fn percent_encode(raw: &str) -> String {
    let mut out = String::with_capacity(raw.len());
    for byte in raw.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(byte as char)
            }
            _ => out.push_str(&format!("%{byte:02X}")),
        }
    }
    out
}

/// One-shot pull for the page this process was launched with (`--page`,
/// e.g. from a desktop file or CLI deep link). Pulled by the frontend on
/// mount rather than pushed as an event, to avoid a race against the
/// webview's JS not having registered its "navigate" listener yet.
#[tauri::command]
fn take_pending_page(state: tauri::State<PendingPage>) -> Option<String> {
    state.0.lock().unwrap().take()
}

fn main() {
    let initial_page = extract_page_arg(&std::env::args().collect::<Vec<_>>());

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, argv, _cwd| {
            // A second launch forwards here instead of opening a second
            // window — same "single instance, focus the existing one"
            // contract instance_ipc.py gives the current Qt Hub. Unlike
            // the initial-launch case, the webview is already up by now,
            // so this pushes the event directly instead of going through
            // PendingPage.
            let page = extract_page_arg(&argv);
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
                if let Some(page) = page {
                    let _ = window.emit("navigate", page);
                }
            }
        }))
        .manage(PendingPage(Mutex::new(initial_page)))
        .invoke_handler(tauri::generate_handler![
            probe_backend, guardian_snapshot, guardian_check, guardian_check_status, guardian_control, privileged_action, privileged_action_status, hardware_snapshot, storage_snapshot, telemetry_recent, gaming_library, starter_packs, familiar_apps, appstream_search, appimage_list, installed_flatpaks, uninstall_flatpak, make_appimage_executable, import_appimage, launch_appimage, install_flatpak, install_status, protondb_lookup_many, anti_cheat_table, take_pending_page, just_list, just_run, just_run_status,
            bootc_upgrade, bootc_rollback, bootc_switch_branch, guardian_execute_recipe, branch_display_name, update_availability_view, mok_status, fonts_ready, mesa_version, mesa_overlay_dry_run, smb_browse, smb_mount_command, memory_pressure, snapshot_count, gaming_slice_command, is_gaming_slice_available, cloud_oauth_status, rclone_oauth_command, ipp_discover, printer_setup_command, btrfs_health, loaded_kernel_modules, pci_devices_by_class, controllers_detect, hardware_view_summary, network_identity, pending_updates_summary, rollback_command, available_audio_presets, apply_pipewire_quantum, deployment_history, recovery_status, update_status, is_live_session, strip_ansi, disk_write_bytes, firmware_updates_count, firmware_devices_command, plasma_presets, apply_plasma_preset, amd64_manifest_entry, collect_availability, ntfs_devices, boot_runtime_checks, desktop_stack_checks, updater_available, current_user_name, open_feedback_issue
        ])
        .run(tauri::generate_context!())
        .expect("error while running the Kyth Hub shell");
}
