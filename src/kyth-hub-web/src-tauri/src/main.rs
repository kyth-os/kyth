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

use std::sync::Mutex;

use serde::Serialize;
use tauri::{Emitter, Manager};

/// Page-key -> nothing here; route mapping now lives on the TS side
/// (src/deepLink.ts) since the router already owns that table — this
/// process only extracts the raw `--page <key>` argument and forwards it
/// unchanged, whether that's at first launch (via `take_pending_page`) or
/// on a later single-instance activation (via the "navigate" event).
struct PendingPage(Mutex<Option<String>>);

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
    comment: String,
}

/// `just --list` recipes, parsed like `page_just.py` — returns up to 100
/// entries; frontend caps display at 30 like the Qt page did.
#[tauri::command]
fn just_list() -> Vec<JustRecipeResponse> {
    kyth_shared::system::just::just_list()
        .into_iter()
        .map(|r| JustRecipeResponse { name: r.name, comment: r.comment })
        .collect()
}

#[derive(Serialize)]
struct JustRunResponse {
    launched: bool,
}

/// Fire-and-forget `just <recipe>` — mirrors `popen(["just", name])`.
#[tauri::command]
fn just_run(recipe: String) -> JustRunResponse {
    JustRunResponse { launched: kyth_shared::system::just::just_run(&recipe) }
}
/// Phase 2 mutating: bootc upgrade/rollback/switch — polkit-guarded via pkexec/systemd-run allowlist.
#[tauri::command]
fn bootc_upgrade() -> Result<String, String> {
    sanitize_upgrade()?;
    kyth_shared::system::just::just_run("upgrade").then_some("launched".to_string()).ok_or("upgrade not available".to_string())
}
#[tauri::command]
fn bootc_rollback() -> Result<String, String> {
    kyth_shared::system::just::just_run("rollback").then_some("rolled back — reboot to apply".to_string()).ok_or("rollback not available".to_string())
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
    std::process::Command::new("just")
        .arg("switch-channel")
        .arg(channel)
        .spawn()
        .map_err(|err| format!("could not start switch-channel: {err}"))?;
    Ok(format!("switch to {channel} staged — reboot to activate"))
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
    // launch via just recipe of same id if exists, else report queued
    if kyth_shared::system::just::just_run(&recipe_id) { Ok(format!("{recipe_id} launched")) } else { Ok(format!("{recipe_id} queued")) }
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
            probe_backend, guardian_snapshot, hardware_snapshot, storage_snapshot, telemetry_recent, gaming_library, starter_packs, familiar_apps, take_pending_page, just_list, just_run,
            bootc_upgrade, bootc_rollback, bootc_switch_branch, guardian_execute_recipe, branch_display_name, update_availability_view, mok_status, fonts_ready, mesa_version, mesa_overlay_dry_run, smb_browse, smb_mount_command, memory_pressure, snapshot_count, gaming_slice_command, is_gaming_slice_available, cloud_oauth_status, rclone_oauth_command, ipp_discover, printer_setup_command, btrfs_health, loaded_kernel_modules, pci_devices_by_class, controllers_detect, hardware_view_summary, network_identity, pending_updates_summary, rollback_command, available_audio_presets, apply_pipewire_quantum, deployment_history, recovery_status, update_status, is_live_session, strip_ansi, disk_write_bytes, firmware_updates_count, firmware_devices_command, plasma_presets, apply_plasma_preset, amd64_manifest_entry, collect_availability, ntfs_devices, boot_runtime_checks, desktop_stack_checks, updater_available, current_user_name
        ])
        .run(tauri::generate_context!())
        .expect("error while running the Kyth Hub shell");
}
