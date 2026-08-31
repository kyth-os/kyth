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
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::OpenOptionsExt;
use std::path::PathBuf;
use std::sync::{Mutex, OnceLock};

use serde::{Deserialize, Serialize};
use tauri::{Emitter, Manager};

mod commands;

/// Page-key -> nothing here; route mapping now lives on the TS side
/// (src/deepLink.ts) since the router already owns that table — this
/// process only extracts the raw `--page <key>` argument and forwards it
/// unchanged, whether that's at first launch (via `take_pending_page`) or
/// on a later single-instance activation (via the "navigate" event).
struct PendingPage(Mutex<Option<String>>);

static APP_INSTALLS: OnceLock<Mutex<HashMap<String, (String, String)>>> = OnceLock::new();
fn app_installs() -> &'static Mutex<HashMap<String, (String, String)>> {
    APP_INSTALLS.get_or_init(|| Mutex::new(HashMap::new()))
}
static GUARDIAN_CHECKS: OnceLock<Mutex<HashMap<String, (String, String)>>> = OnceLock::new();
fn guardian_checks() -> &'static Mutex<HashMap<String, (String, String)>> {
    GUARDIAN_CHECKS.get_or_init(|| Mutex::new(HashMap::new()))
}

fn extract_page_arg<S: AsRef<str>>(argv: &[S]) -> Option<String> {
    argv.iter()
        .position(|a| a.as_ref() == "--page")
        .and_then(|i| argv.get(i + 1))
        .map(|s| s.as_ref().to_string())
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

    GuardianSnapshotResponse {
        pending_count: pending.len(),
        pending: pending_response,
        history: history_response,
    }
}

/// Ask the existing Python Guardian service for a fresh check, then let the
/// frontend re-read the disk-backed snapshot.  The Rust shell does not port
/// the live probe sweep; Python remains the authority for that behavior.
#[tauri::command]
fn guardian_check(investigate: bool) -> Result<String, String> {
    if !std::path::Path::new("/usr/bin/kyth-guardian").exists() {
        return Err("Guardian service is not installed".to_string());
    }
    let job = format!(
        "guardian-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    guardian_checks().lock().unwrap().insert(
        job.clone(),
        ("running".into(), "Guardian check is running…".into()),
    );
    let job_for_thread = job.clone();
    std::thread::spawn(move || {
        let action = if investigate { "investigate" } else { "check" };
        let result = commands::process::output("/usr/bin/kyth-guardian", &["--json", action]);
        let (state, detail) = match result {
            Ok(output) if output.status.success() => {
                ("complete", "Guardian check complete.".to_string())
            }
            Ok(output) => ("failed", commands::process::bounded_text(&output.stderr)),
            Err(error) => ("failed", format!("Could not start Guardian: {error}")),
        };
        guardian_checks()
            .lock()
            .unwrap()
            .insert(job_for_thread, (state.into(), detail));
    });
    Ok(job)
}

#[tauri::command]
fn guardian_check_status(job: String) -> InstallStatus {
    let (state, detail) = guardian_checks()
        .lock()
        .unwrap()
        .get(&job)
        .cloned()
        .unwrap_or(("unknown".into(), "Guardian job not found.".into()));
    InstallStatus {
        id: job,
        state,
        detail,
    }
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
    let job = format!(
        "guardian-control-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    guardian_checks().lock().unwrap().insert(
        job.clone(),
        ("running".into(), format!("Running Guardian {action}…")),
    );
    let job_for_thread = job.clone();
    std::thread::spawn(move || {
        let result = commands::process::output("/usr/bin/kyth-guardian", args);
        let (state, detail) = match result {
            Ok(output) if output.status.success() => {
                ("complete", commands::process::bounded_text(&output.stdout))
            }
            Ok(output) => ("failed", commands::process::bounded_text(&output.stderr)),
            Err(error) => ("failed", format!("Could not start Guardian: {error}")),
        };
        guardian_checks().lock().unwrap().insert(
            job_for_thread,
            (
                state.into(),
                if detail.is_empty() {
                    "Guardian control complete.".into()
                } else {
                    detail
                },
            ),
        );
    });
    Ok(job)
}

/// Phase 2: guardian execute_recipe (Repair/Diagnostics mutating)
#[tauri::command]
fn guardian_execute_recipe(recipe_id: String) -> Result<String, String> {
    let state = kyth_shared::guardian::load_state();
    if !kyth_shared::guardian::is_pending_recipe(&state, &recipe_id) {
        return Err("recipe not pending".to_string());
    }
    // Guardian ids are dotted (`audio.restart`) and are not just recipes —
    // handing them to `just_run` ran nothing and reported "launched" for
    // every one of them, advisory notifications included. `execute_recipe`
    // carries guardian.py's own eligibility gate and runs the recipe's argv.
    let detail = kyth_shared::guardian::execute_recipe(&recipe_id)?;
    Ok(format!(
        "{}: {detail}",
        kyth_shared::guardian::recipe_title(&recipe_id)
    ))
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
    MokStatusResponse {
        sb_state: s.sb_state,
        enrolled: s.enrolled,
    }
}

#[derive(serde::Serialize)]
struct FontsReadyResponse {
    ready: bool,
    detail: String,
}
#[tauri::command]
fn fonts_ready() -> FontsReadyResponse {
    let (ready, detail) = kyth_shared::system::fonts_ready::fonts_ready();
    FontsReadyResponse { ready, detail }
}

#[tauri::command]
fn mesa_version() -> String {
    kyth_shared::system::mesa_version::mesa_version()
}
#[derive(serde::Serialize)]
struct MesaOverlayResponse {
    ok: bool,
    detail: String,
}
#[tauri::command]
fn mesa_overlay_dry_run() -> MesaOverlayResponse {
    let (ok, detail) = kyth_shared::system::mesa_version::mesa_overlay_dry_run();
    MesaOverlayResponse { ok, detail }
}

#[derive(serde::Serialize)]
struct SmbBrowseResponse {
    ok: bool,
    detail: String,
}
#[tauri::command]
fn smb_browse(host: Option<String>) -> SmbBrowseResponse {
    let (ok, detail) = kyth_shared::system::smb::smb_browse_dry_run(host.as_deref());
    SmbBrowseResponse { ok, detail }
}
#[tauri::command]
fn smb_mount_command(share: String) -> Vec<String> {
    kyth_shared::system::smb::smb_mount_command(&share)
}

/// Non-secret metadata saved by the legacy Hub after its root helper has
/// created a share. Passwords deliberately never enter this file.
#[derive(Clone, Deserialize, Serialize)]
struct SmbConfiguredShare {
    name: String,
    server: String,
    share_path: String,
    mount_point: String,
    username: String,
    #[serde(default)]
    domain: String,
    #[serde(default)]
    auto_mount: bool,
}

fn smb_config_path() -> Result<PathBuf, String> {
    let home = std::env::var_os("HOME")
        .ok_or_else(|| "could not locate the current user's home directory".to_string())?;
    Ok(PathBuf::from(home).join(".config/kyth-smb-shares.json"))
}

fn valid_smb_configured_share(share: &SmbConfiguredShare) -> bool {
    let valid_text = |value: &str, maximum: usize| {
        !value.is_empty() && value.len() <= maximum && !value.chars().any(char::is_control)
    };
    let valid_name = !share.name.is_empty()
        && share.name.len() <= 64
        && share
            .name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-'));
    let approved_mount = ["/mnt/", "/media/", "/run/media/", "/home/"];
    valid_name
        && valid_text(&share.server, 253)
        && valid_text(&share.share_path, 4096)
        && valid_text(&share.mount_point, 4096)
        && valid_text(&share.username, 256)
        && share.domain.len() <= 256
        && !share.domain.chars().any(char::is_control)
        && approved_mount
            .iter()
            .any(|prefix| share.mount_point.starts_with(prefix))
        && !share.mount_point.contains("//")
        && !share.mount_point.split('/').any(|part| part == "..")
}

fn load_smb_configured_shares() -> Vec<SmbConfiguredShare> {
    let Ok(path) = smb_config_path() else {
        return Vec::new();
    };
    let Ok(raw) = fs::read_to_string(path) else {
        return Vec::new();
    };
    serde_json::from_str::<Vec<SmbConfiguredShare>>(&raw)
        .unwrap_or_default()
        .into_iter()
        .filter(valid_smb_configured_share)
        .collect()
}

fn save_smb_configured_shares(shares: &[SmbConfiguredShare]) -> Result<(), String> {
    let path = smb_config_path()?;
    let parent = path
        .parent()
        .ok_or_else(|| "invalid SMB configuration path".to_string())?;
    fs::create_dir_all(parent)
        .map_err(|error| format!("could not create SMB configuration directory: {error}"))?;
    let raw = serde_json::to_string_pretty(shares)
        .map_err(|error| format!("could not encode SMB configuration: {error}"))?;
    let mut file = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .mode(0o600)
        .open(&path)
        .map_err(|error| format!("could not save SMB configuration: {error}"))?;
    file.write_all(raw.as_bytes())
        .map_err(|error| format!("could not save SMB configuration: {error}"))?;
    file.write_all(b"\n")
        .map_err(|error| format!("could not save SMB configuration: {error}"))?;
    file.sync_all()
        .map_err(|error| format!("could not finish SMB configuration: {error}"))?;
    Ok(())
}

#[tauri::command]
fn smb_configured_shares() -> Vec<SmbConfiguredShare> {
    load_smb_configured_shares()
}

#[tauri::command]
fn smb_save_configured_share(share: SmbConfiguredShare) -> Result<(), String> {
    if !valid_smb_configured_share(&share) {
        return Err("invalid SMB share configuration".to_string());
    }
    let mut shares = load_smb_configured_shares();
    shares.retain(|existing| existing.name != share.name);
    shares.push(share);
    save_smb_configured_shares(&shares)
}

#[tauri::command]
fn smb_remove_configured_share(name: String) -> Result<(), String> {
    if name.is_empty()
        || name.len() > 64
        || !name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-'))
    {
        return Err("invalid SMB share name".to_string());
    }
    let mut shares = load_smb_configured_shares();
    shares.retain(|existing| existing.name != name);
    save_smb_configured_shares(&shares)
}

#[derive(serde::Serialize)]
struct MemoryPressureResponse {
    status: String,
    detail: String,
}
#[tauri::command]
fn memory_pressure() -> MemoryPressureResponse {
    let (status, detail) = kyth_shared::system::memory_pressure::memory_pressure_status();
    MemoryPressureResponse { status, detail }
}
#[tauri::command]
fn snapshot_count() -> usize {
    kyth_shared::system::snapshot::snapshot_count()
}

#[tauri::command]
fn snapshot_timeline(limit: Option<usize>) -> Vec<kyth_shared::system::snapshot::SnapshotRow> {
    kyth_shared::system::snapshot::snapshot_timeline(limit.unwrap_or(20).min(100))
}

#[tauri::command]
fn gaming_slice_command(argv: Vec<String>, use_user: Option<bool>) -> Vec<String> {
    kyth_shared::system::gaming_slice::gaming_slice_command(&argv, use_user)
}
#[tauri::command]
fn is_gaming_slice_available() -> bool {
    kyth_shared::system::gaming_slice::is_gaming_slice_available()
}

#[derive(serde::Serialize)]
struct CloudOauthResponse {
    ok: bool,
    detail: String,
}
#[tauri::command]
fn cloud_oauth_status() -> CloudOauthResponse {
    let (ok, detail) = kyth_shared::system::cloud_oauth::cloud_oauth_status();
    CloudOauthResponse { ok, detail }
}
#[tauri::command]
fn rclone_oauth_command(remote: String) -> Vec<String> {
    kyth_shared::system::cloud_oauth::rclone_oauth_command(&remote)
}

/// The legacy Cloud Storage page owns OAuth tokens and rclone execution.
/// The Hub may safely surface this *non-secret* sync metadata so users can
/// see which local folders are connected without opening the legacy page.
#[derive(Serialize)]
struct CloudSyncRemote {
    name: String,
    service: String,
    folder: String,
    last_sync: Option<f64>,
    last_ok: Option<bool>,
}

fn cloud_sync_config_path() -> Result<PathBuf, String> {
    let home = std::env::var_os("HOME")
        .ok_or_else(|| "could not locate the current user's home directory".to_string())?;
    Ok(PathBuf::from(home).join(".config/kyth-cloud-sync.json"))
}

fn valid_cloud_sync_remote(name: &str, info: &serde_json::Value) -> Option<CloudSyncRemote> {
    let valid_text = |value: &str, maximum: usize| {
        !value.is_empty() && value.len() <= maximum && !value.chars().any(char::is_control)
    };
    if !valid_text(name, 64) {
        return None;
    }
    let object = info.as_object()?;
    let service = object.get("service")?.as_str()?;
    let folder = object.get("folder")?.as_str()?;
    if !matches!(service, "drive" | "onedrive" | "dropbox") || !valid_text(folder, 4096) {
        return None;
    }
    Some(CloudSyncRemote {
        name: name.to_string(),
        service: service.to_string(),
        folder: folder.to_string(),
        last_sync: object.get("last_sync").and_then(serde_json::Value::as_f64),
        last_ok: object.get("last_ok").and_then(serde_json::Value::as_bool),
    })
}

#[tauri::command]
fn cloud_sync_remotes() -> Vec<CloudSyncRemote> {
    let Ok(path) = cloud_sync_config_path() else {
        return Vec::new();
    };
    // Do not follow an attacker-controlled link from the user config dir.
    let Ok(metadata) = fs::symlink_metadata(&path) else {
        return Vec::new();
    };
    if !metadata.is_file() || metadata.len() > 128 * 1024 {
        return Vec::new();
    }
    let Ok(raw) = fs::read_to_string(path) else {
        return Vec::new();
    };
    let Ok(entries) = serde_json::from_str::<HashMap<String, serde_json::Value>>(&raw) else {
        return Vec::new();
    };
    let mut remotes: Vec<_> = entries
        .iter()
        .filter_map(|(name, info)| valid_cloud_sync_remote(name, info))
        .collect();
    remotes.sort_by(|left, right| left.name.cmp(&right.name));
    remotes
}

#[tauri::command]
fn open_cloud_storage_app() -> Result<String, String> {
    std::process::Command::new("/usr/bin/kyth-welcome-launch")
        .args(["--page", "Cloud Storage"])
        .spawn()
        .map_err(|error| format!("could not open Cloud Storage: {error}"))?;
    Ok("Opened the full Cloud Storage workflow.".to_string())
}

#[tauri::command]
fn open_move_files_app() -> Result<String, String> {
    std::process::Command::new("/usr/bin/kyth-welcome-launch")
        .args(["--page", "Move Files"])
        .spawn()
        .map_err(|error| format!("could not open Move Files: {error}"))?;
    Ok("Opened the full Windows migration workflow.".to_string())
}

#[tauri::command]
fn open_network_shares_app() -> Result<String, String> {
    std::process::Command::new("/usr/bin/kyth-welcome-launch")
        .args(["--page", "Network Shares"])
        .spawn()
        .map_err(|error| format!("could not open Network Shares: {error}"))?;
    Ok("Opened the full Network Shares workflow.".to_string())
}
#[tauri::command]
fn ipp_discover() -> Vec<String> {
    kyth_shared::system::printing::ipp_discover()
}
#[tauri::command]
fn printer_setup_command() -> Vec<String> {
    kyth_shared::system::printing::printer_setup_command()
}

#[derive(serde::Serialize)]
struct BtrfsHealthResponse {
    status: String,
    detail: String,
}
#[tauri::command]
fn btrfs_health() -> BtrfsHealthResponse {
    let (status, detail) = kyth_shared::system::btrfs_status::btrfs_health_summary();
    BtrfsHealthResponse { status, detail }
}
#[tauri::command]
fn loaded_kernel_modules() -> Vec<String> {
    kyth_shared::system::drivers::get_loaded_kernel_modules()
        .into_iter()
        .collect()
}
#[tauri::command]
fn pci_devices_by_class(class: String) -> Vec<String> {
    kyth_shared::system::drivers::get_pci_devices_by_class(&class)
}

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
    usb_controllers: Vec<(String, String)>,
    input_nodes: Vec<String>,
    xone_dongle: bool,
    xone_loaded: bool,
    xpadneo_loaded: bool,
    hid_ps_loaded: bool,
    dualsense_found: bool,
}

#[tauri::command]
fn hardware_view_summary() -> Option<HardwareViewSummaryResponse> {
    kyth_shared::system::hardware_view::get_hardware_view_summary().map(|v| {
        HardwareViewSummaryResponse {
            has_nvidia: v.has_nvidia,
            is_hybrid: v.is_hybrid,
            capabilities: v.capabilities,
        }
    })
}
#[derive(serde::Serialize)]
struct HardwareViewSummaryResponse {
    has_nvidia: bool,
    is_hybrid: bool,
    capabilities: Vec<String>,
}

#[tauri::command]
fn network_identity() -> NetworkIdentityResponse {
    let n = kyth_shared::system::network_identity::get_network_identity();
    NetworkIdentityResponse {
        vpn_connected: n.vpn_connected,
        vpn_name: n.vpn_name,
        smb_mounts: n.smb_mounts,
        cloud_providers: n.cloud_providers,
        detail: n.detail,
    }
}
#[derive(serde::Serialize)]
struct NetworkIdentityResponse {
    vpn_connected: bool,
    vpn_name: String,
    smb_mounts: i32,
    cloud_providers: Vec<String>,
    detail: String,
}

#[tauri::command]
fn rollback_command() -> Vec<String> {
    kyth_shared::system::updates_unified::rollback_command()
}

#[tauri::command]
fn available_audio_presets() -> Vec<String> {
    kyth_shared::system::pipewire::available_audio_presets()
}
#[derive(serde::Serialize)]
struct PipewireApplyResponse {
    ok: bool,
    detail: String,
}
#[tauri::command]
fn apply_pipewire_quantum(preset: String, dry_run: bool) -> PipewireApplyResponse {
    let (ok, detail) = kyth_shared::system::pipewire::apply_pipewire_quantum(&preset, dry_run);
    PipewireApplyResponse { ok, detail }
}

#[tauri::command]
fn deployment_history() -> Vec<DeploymentInfoResponse> {
    kyth_shared::system::deployment_history::deployment_history()
        .into_iter()
        .map(|d| DeploymentInfoResponse {
            section: d.section,
            label: d.label,
            available: d.available,
            reference: d.reference,
            branch: d.branch,
            timestamp: d.timestamp,
            digest: d.digest,
            short_digest: d.short_digest,
            status_text: d.status_text,
        })
        .collect()
}
#[derive(serde::Serialize)]
struct DeploymentInfoResponse {
    section: String,
    label: String,
    available: bool,
    reference: Option<String>,
    branch: Option<String>,
    timestamp: Option<String>,
    digest: Option<String>,
    short_digest: Option<String>,
    status_text: String,
}

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
    commands::privilege::validate_flatpak_id(&app_id)?;
    let scope = kyth_shared::system::software_catalog::installed_flatpaks()
        .into_iter()
        .find(|app| app.id == app_id)
        .map(|app| app.scope)
        .ok_or_else(|| "that Flatpak is not installed".to_string())?;
    let job = format!(
        "flatpak-uninstall-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    app_installs().lock().unwrap().insert(
        job.clone(),
        ("running".into(), format!("Uninstalling {app_id}…")),
    );
    let job_for_thread = job.clone();
    std::thread::spawn(move || {
        let result: Result<(bool, String), String> = if scope == "system" {
            privileged_flatpak_uninstall(&app_id).map(|detail| (true, detail))
        } else {
            std::process::Command::new("flatpak")
                .args(["uninstall", "--user", "-y", &app_id])
                .output()
                .map(|output| {
                    if output.status.success() {
                        (true, format!("Uninstalled {app_id}."))
                    } else {
                        (
                            false,
                            String::from_utf8_lossy(&output.stderr)
                                .trim()
                                .chars()
                                .take(400)
                                .collect(),
                        )
                    }
                })
                .map_err(|err| err.to_string())
        };
        let (state, detail) = match result {
            Ok((true, detail)) => ("complete", detail),
            Ok((false, detail)) => ("failed", detail),
            Err(err) => ("failed", format!("Could not uninstall Flatpak: {err}")),
        };
        app_installs()
            .lock()
            .unwrap()
            .insert(job_for_thread, (state.into(), detail));
    });
    Ok(job)
}

fn privileged_flatpak_uninstall(app_id: &str) -> Result<String, String> {
    commands::privilege::flatpak_uninstall(app_id)
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
    let allowed = kyth_shared::system::software_catalog::appimages()
        .into_iter()
        .any(|app| app.path == path && app.executable);
    if !allowed {
        return Err(
            "AppImage is not a discovered executable in an allowed user directory".to_string(),
        );
    }
    std::process::Command::new(&path)
        .spawn()
        .map(|_| "AppImage launched.".to_string())
        .map_err(|err| format!("could not launch AppImage: {err}"))
}

#[derive(serde::Serialize)]
pub(crate) struct InstallStatus {
    id: String,
    state: String,
    detail: String,
}

#[tauri::command]
fn install_flatpak(app_id: String) -> Result<String, String> {
    commands::privilege::validate_flatpak_id(&app_id)?;
    let job = format!(
        "flatpak-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    app_installs().lock().unwrap().insert(
        job.clone(),
        ("running".into(), format!("Installing {app_id}…")),
    );
    let job_for_thread = job.clone();
    std::thread::spawn(move || {
        let result = std::process::Command::new("flatpak")
            .args(["install", "--user", "-y", "flathub", &app_id])
            .output();
        let (state, detail) = match result {
            Ok(output) if output.status.success() => {
                ("complete", "Installation complete.".to_string())
            }
            Ok(output) => (
                "failed",
                String::from_utf8_lossy(&output.stderr)
                    .trim()
                    .chars()
                    .take(400)
                    .collect(),
            ),
            Err(err) => ("failed", format!("Could not start Flatpak: {err}")),
        };
        app_installs()
            .lock()
            .unwrap()
            .insert(job_for_thread, (state.into(), detail));
    });
    Ok(job)
}

#[tauri::command]
fn install_status(job: String) -> InstallStatus {
    let (state, detail) = app_installs()
        .lock()
        .unwrap()
        .get(&job)
        .cloned()
        .unwrap_or(("unknown".into(), "Installation job not found.".into()));
    InstallStatus {
        id: job,
        state,
        detail,
    }
}

#[tauri::command]
fn protondb_lookup_many(
    app_ids: Vec<String>,
) -> Vec<kyth_shared::system::gaming_compat::ProtonDbResult> {
    kyth_shared::system::gaming_compat::protondb_lookup_many(&app_ids)
}

#[tauri::command]
fn anti_cheat_table() -> Vec<kyth_shared::system::gaming_compat::AntiCheatEntry> {
    kyth_shared::system::gaming_compat::anti_cheat_table()
}

#[derive(serde::Serialize, serde::Deserialize)]
struct CompatibilityGameResponse {
    name: String,
    anticheat: String,
    status: String,
    note: String,
    checked: String,
    source: String,
    source_url: String,
}

#[derive(serde::Deserialize)]
struct CompatibilityBundle {
    #[serde(default)]
    games: Vec<CompatibilityGameResponse>,
}

/// The same bundled compatibility matrix used by the legacy Hub. Keeping the
/// data in the image-owned JSON means Tauri and Qt show the same title list;
/// the frontend only owns filtering and presentation.
#[tauri::command]
fn compatibility_games() -> Vec<CompatibilityGameResponse> {
    const BUNDLED: &str = include_str!("../../../kyth-welcome/kyth_welcome/compat_games.json");
    serde_json::from_str::<CompatibilityBundle>(BUNDLED)
        .map(|bundle| bundle.games)
        .unwrap_or_default()
}

#[tauri::command]
fn telemetry_recent(limit: Option<u32>) -> Vec<kyth_shared::system::telemetry::SessionRow> {
    kyth_shared::system::telemetry::recent_sessions(limit.unwrap_or(15) as usize)
}

#[tauri::command]
fn is_live_session() -> bool {
    kyth_shared::system::process::is_live_session()
}
#[tauri::command]
fn strip_ansi(text: String) -> String {
    kyth_shared::system::process::strip_ansi(&text)
}
#[tauri::command]
fn disk_write_bytes() -> u64 {
    kyth_shared::system::process::get_disk_write_bytes()
}

#[tauri::command]
fn firmware_updates_count() -> i32 {
    kyth_shared::system::firmware::check_firmware_updates(20)
}
#[tauri::command]
fn firmware_devices_command() -> Vec<String> {
    kyth_shared::system::firmware::firmware_devices_command()
}

#[tauri::command]
fn plasma_presets() -> Vec<String> {
    kyth_shared::system::plasma_hdr::available_presets()
}
#[derive(serde::Serialize)]
struct PlasmaApplyResponse {
    ok: bool,
    detail: String,
}
#[tauri::command]
fn apply_plasma_preset(preset: String, dry_run: bool) -> PlasmaApplyResponse {
    let (ok, detail) = kyth_shared::system::plasma_hdr::apply_preset(&preset, dry_run);
    PlasmaApplyResponse { ok, detail }
}

#[tauri::command]
fn amd64_manifest_entry(manifest: serde_json::Value) -> Option<serde_json::Value> {
    kyth_shared::system::registry::amd64_manifest_entry(&manifest)
}

#[tauri::command]
fn ntfs_devices() -> Vec<serde_json::Value> {
    kyth_shared::system::drives::get_ntfs_devices()
}

#[tauri::command]
fn migration_readiness() -> kyth_shared::system::windows_verify::WindowsParity {
    let home = std::env::var_os("HOME").map(std::path::PathBuf::from).unwrap_or_default();
    kyth_shared::system::windows_verify::verify(home, std::path::Path::new("/var/home").exists())
}

/// The existing Python VPN utility owns the profile editor and SAML browser
/// flow. This fixed launch path makes that complete workflow reachable from
/// the default Tauri Hub without accepting arbitrary commands or arguments.
#[tauri::command]
fn open_vpn_app() -> Result<String, String> {
    std::process::Command::new("/usr/bin/kyth-vpn-connect")
        .spawn()
        .map_err(|error| format!("could not open the VPN connection app: {error}"))?;
    Ok("Opened the full VPN connection app.".to_string())
}

#[tauri::command]
fn desktop_stack_checks() -> Vec<kyth_shared::system::desktop_stack::StackCheck> {
    kyth_shared::system::desktop_stack::desktop_stack_checks()
}

/// Opens a prefilled `kyth-os/kyth` issue in the user's browser — the
/// Feedback section's actual send path. Host and repo are fixed here
/// rather than passed in; only the title and body travel from the
/// frontend, and both are percent-encoded before they reach `xdg-open`,
/// so this can't be pointed at an arbitrary URL.
#[tauri::command]
fn open_feedback_issue(title: String, body: String) -> Result<String, String> {
    // Scrub logs before they cross the public-report boundary, even if a
    // future caller bypasses the retired Python Feedback page's scrub step.
    let body = kyth_shared::diagnostics_scrub::scrub_logs(&body);
    let url = kyth_shared::diagnostic_report::github_issue_url(
        "https://github.com/kyth-os/kyth",
        &title,
        &body,
        None,
    );
    std::process::Command::new("xdg-open")
        .arg(&url)
        .spawn()
        .map_err(|err| format!("could not open browser: {err}"))?;
    Ok("Opened a prefilled issue in your browser.".to_string())
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
            commands::dashboard::probe_backend,
            guardian_snapshot,
            guardian_check,
            guardian_check_status,
            guardian_control,
            commands::privilege::privileged_action,
            commands::privilege::privileged_action_status,
            commands::dashboard::hardware_snapshot,
            commands::dashboard::storage_snapshot,
            telemetry_recent,
            gaming_library,
            starter_packs,
            familiar_apps,
            appstream_search,
            appimage_list,
            installed_flatpaks,
            uninstall_flatpak,
            make_appimage_executable,
            import_appimage,
            launch_appimage,
            install_flatpak,
            install_status,
            protondb_lookup_many,
            anti_cheat_table,
            compatibility_games,
            take_pending_page,
            commands::updates::just_list,
            commands::updates::just_run,
            commands::updates::bootc_upgrade,
            commands::updates::bootc_rollback,
            commands::updates::bootc_switch_branch,
            guardian_execute_recipe,
            commands::updates::branch_display_name,
            commands::updates::update_availability_view,
            mok_status,
            fonts_ready,
            mesa_version,
            mesa_overlay_dry_run,
            smb_browse,
            smb_mount_command,
            smb_configured_shares,
            smb_save_configured_share,
            smb_remove_configured_share,
            memory_pressure,
            snapshot_count,
            snapshot_timeline,
            gaming_slice_command,
            is_gaming_slice_available,
            cloud_oauth_status,
            rclone_oauth_command,
            cloud_sync_remotes,
            open_cloud_storage_app,
            open_move_files_app,
            open_network_shares_app,
            ipp_discover,
            printer_setup_command,
            btrfs_health,
            loaded_kernel_modules,
            pci_devices_by_class,
            controllers_detect,
            hardware_view_summary,
            network_identity,
            commands::updates::pending_updates_summary,
            rollback_command,
            available_audio_presets,
            apply_pipewire_quantum,
            deployment_history,
            commands::dashboard::recovery_status,
            commands::updates::update_status,
            is_live_session,
            strip_ansi,
            disk_write_bytes,
            firmware_updates_count,
            firmware_devices_command,
            plasma_presets,
            apply_plasma_preset,
            amd64_manifest_entry,
            commands::updates::collect_availability,
            ntfs_devices,
            migration_readiness,
            open_vpn_app,
            commands::dashboard::boot_runtime_checks,
            desktop_stack_checks,
            commands::updates::updater_available,
            commands::dashboard::current_user_name,
            open_feedback_issue
        ])
        .run(tauri::generate_context!())
        .expect("error while running the Kyth Hub shell");
}
