// Tauri shell for the Kyth Hub web frontend. It owns the native window,
// single-instance behavior, `--page` deep links, and typed Rust commands.
//
// Hub reads and actions cross this typed Rust/Tauri boundary. The React
// frontend owns presentation; native behavior belongs in this crate or the
// shared Rust crate, with fixed external argv only where the OS owns the
// operation. The retired Python Hub is source-only compatibility material and
// is not part of the supported build or runtime path.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::collections::HashMap;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::OpenOptionsExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::{Mutex, OnceLock};

use kyth_shared::system::jobs::{timeout_for, JobStore, JobTimeoutClass};

use serde::{Deserialize, Serialize};
use tauri::{Emitter, Manager};

mod commands;

/// Page-key -> nothing here; route mapping now lives on the TS side
/// (src/deepLink.ts) since the router already owns that table — this
/// process only extracts the raw `--page <key>` argument and forwards it
/// unchanged, whether that's at first launch (via `take_pending_page`) or
/// on a later single-instance activation (via the "navigate" event).
struct PendingPage(Mutex<Option<String>>);

/// File supplied by the native MIME-handler launcher. Kept separate from page
/// deep links so a filename can never be interpreted as a Hub route.
struct PendingExeHandler(Mutex<Option<String>>);

/// Bounded job stores (cap + TTL eviction + cancellation); see
/// `kyth_shared::system::jobs` for the contract that replaced the previous
/// grow-forever `HashMap` stores.
static APP_INSTALLS: OnceLock<JobStore> = OnceLock::new();
fn app_installs() -> &'static JobStore {
    APP_INSTALLS.get_or_init(JobStore::default)
}
static GUARDIAN_CHECKS: OnceLock<JobStore> = OnceLock::new();
fn guardian_checks() -> &'static JobStore {
    GUARDIAN_CHECKS.get_or_init(JobStore::default)
}

static FOCUS_SESSIONS: OnceLock<Mutex<HashMap<String, Child>>> = OnceLock::new();
fn focus_sessions() -> &'static Mutex<HashMap<String, Child>> {
    FOCUS_SESSIONS.get_or_init(|| Mutex::new(HashMap::new()))
}

fn extract_page_arg<S: AsRef<str>>(argv: &[S]) -> Option<String> {
    argv.iter()
        .position(|a| a.as_ref() == "--page")
        .and_then(|i| argv.get(i + 1))
        .map(|s| s.as_ref().to_string())
}

fn extract_exe_handler_arg<S: AsRef<str>>(argv: &[S]) -> Option<String> {
    argv.iter()
        .position(|argument| argument.as_ref() == "--exe-handler")
        .and_then(|index| argv.get(index + 1))
        .map(|argument| argument.as_ref().to_string())
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

/// Ask the installed native Rust Guardian service for a fresh check, then let
/// the frontend re-read the disk-backed snapshot. The service currently owns
/// the deterministic core sweep and state writer; extended/model-assisted
/// probes remain an explicitly tracked parity gap.
#[derive(serde::Serialize)]
struct GuardianActionLaunch {
    job: String,
    state: String,
    detail: String,
}
#[tauri::command]
fn guardian_check(investigate: bool) -> Result<GuardianActionLaunch, String> {
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
    let (job, _) = guardian_checks().start(&job, "Guardian check is running…".into());
    let job_for_thread = job.clone();
    std::thread::spawn(move || {
        let action = if investigate { "investigate" } else { "check" };
        let result = commands::process::output("/usr/bin/kyth-guardian", &["--json", action]);
        let (state, detail) = match result {
            Ok(output) if output.status.success() => {
                ("complete", "Guardian check complete.".to_string())
            }
            Ok(output) => {
                // An empty stderr would surface as a blank failure in the
                // UI; fall back to the exit code like guardian_control does.
                let detail = commands::process::bounded_text(&output.stderr);
                let detail = if detail.is_empty() {
                    match output.status.code() {
                        Some(code) => format!("Guardian check failed (exit {code})."),
                        None => "Guardian check stopped before it could complete.".to_string(),
                    }
                } else {
                    detail
                };
                ("failed", detail)
            }
            Err(error) => ("failed", format!("Could not start Guardian: {error}")),
        };
        guardian_checks().finish(&job_for_thread, state, detail);
    });
    Ok(GuardianActionLaunch {
        job,
        state: "running".into(),
        detail: "Guardian check is running…".into(),
    })
}

#[tauri::command]
fn guardian_check_status(job: String) -> InstallStatus {
    let (state, detail) = guardian_checks().status(&job).unwrap_or((
        kyth_shared::system::jobs::STATE_UNKNOWN.into(),
        "Guardian job not found.".into(),
    ));
    InstallStatus {
        id: job,
        state,
        detail,
    }
}

/// Cancel a running Guardian check. The helper itself is already
/// time-bounded; cancelling stops the UI from tracking it further.
#[tauri::command]
fn guardian_check_cancel(job: String) -> InstallStatus {
    guardian_checks().cancel(&job);
    guardian_check_status(job)
}

#[tauri::command]
fn guardian_control(action: String) -> Result<GuardianActionLaunch, String> {
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
    let (job, _) = guardian_checks().start(&job, format!("Running Guardian {action}…"));
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
        guardian_checks().finish(
            &job_for_thread,
            state,
            if detail.is_empty() {
                "Guardian control complete.".into()
            } else {
                detail
            },
        );
    });
    Ok(GuardianActionLaunch {
        job,
        state: "running".into(),
        detail: format!("Running Guardian {action}…"),
    })
}

/// Phase 2: guardian execute_recipe (Repair/Diagnostics mutating)
///
/// Async + spawn_blocking: the recipe runs up to 30s plus verification
/// probes; a sync command pinned a Tauri worker (and the UI's await) for
/// the whole run. The shared single-flight slot in `execute_recipe` makes
/// a double-click return "already running" instead of a second repair.
#[tauri::command]
async fn guardian_execute_recipe(recipe_id: String) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = kyth_shared::guardian::load_state();
        if !kyth_shared::guardian::is_pending_recipe(&state, &recipe_id) {
            return Err("recipe not pending".to_string());
        }
        // Guardian ids are dotted (`audio.restart`) and are not just recipes —
        // handing them to the typed Hub action bridge ran nothing and reported "launched" for
        // every one of them, advisory notifications included. `execute_recipe`
        // carries guardian.py's own eligibility gate and runs the recipe's argv.
        let detail = kyth_shared::guardian::execute_recipe(&recipe_id)?;
        Ok(format!(
            "{}: {detail}",
            kyth_shared::guardian::recipe_title(&recipe_id)
        ))
    })
    .await
    .map_err(|error| format!("Guardian repair task failed: {error}"))?
}

#[tauri::command]
fn guardian_dismiss(recipe_id: String) -> Result<String, String> {
    kyth_shared::guardian::dismiss_recommendation(&recipe_id)
}

#[derive(serde::Serialize)]
struct MokStatusResponse {
    sb_state: String,
    enrolled: String,
}

/// Live Secure Boot + MOK enrollment (N40) — runs mokutil (5s each).
#[tauri::command]
async fn mok_status() -> MokStatusResponse {
    tauri::async_runtime::spawn_blocking(|| {
        let s = kyth_shared::system::mok_verify::mok_status();
        MokStatusResponse {
            sb_state: s.sb_state,
            enrolled: s.enrolled,
        }
    })
    .await
    .unwrap_or(MokStatusResponse {
        sb_state: "unknown".to_string(),
        enrolled: "unknown".to_string(),
    })
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
    if let Some(host) = host.as_deref() {
        if !kyth_shared::system::smb::is_valid_smb_host(host) {
            return SmbBrowseResponse {
                ok: false,
                detail: "invalid SMB host".to_string(),
            };
        }
    }
    let (ok, detail) = kyth_shared::system::smb::smb_browse_dry_run(host.as_deref());
    SmbBrowseResponse { ok, detail }
}
#[tauri::command]
fn smb_mount(share: String) -> Result<String, String> {
    let share = share.trim();
    if share.len() > 2048
        || !share.starts_with("smb://")
        || share
            .chars()
            .any(|character| character.is_control() || character.is_whitespace())
    {
        return Err("Enter a valid SMB share such as smb://server/share.".to_string());
    }
    // Credentials in the URI would sit in the gio child's argv, readable
    // by every local user via /proc for up to 30s. Refuse; the desktop
    // keyring prompt collects them safely.
    if kyth_shared::system::smb::smb_uri_has_userinfo(share) {
        return Err(
            "Enter smb://server/share without a username or password; you'll be prompted for credentials."
                .to_string(),
        );
    }

    // Never echo the raw URI: `smb://user:password@host/share` carries
    // credentials, and these strings reach the UI and the logs. Display
    // host+share only.
    let display = kyth_shared::system::smb::redact_smb_uri(share);
    let argv = kyth_shared::system::smb::smb_mount_command(share);
    // `gio mount` may need auth or fail outright; a detached spawn reports
    // success for a mount that never happened. Run it bounded and report
    // its real exit status instead.
    let output =
        kyth_shared::system::process::run_bounded(&argv, std::time::Duration::from_secs(30))
            .map_err(|error| {
                if error.kind() == std::io::ErrorKind::TimedOut {
                    format!("Mounting {display} took too long and was stopped.")
                } else {
                    format!("could not start the desktop share mount: {error}")
                }
            })?;
    if output.status.success() {
        Ok(format!("Mounted {display}."))
    } else {
        let detail = commands::process::bounded_text(&output.stderr);
        if detail.is_empty() {
            Err(format!(
                "Could not mount {display} (exit {}).",
                output.status.code().unwrap_or(-1)
            ))
        } else {
            Err(format!("Could not mount {display}: {detail}"))
        }
    }
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
    // Atomic write (temp + fsync + rename): truncating the live file first
    // means a crash or power loss mid-save leaves an empty/corrupt JSON
    // and every saved share is lost. Same pattern as guardian state.
    kyth_shared::atomic_io::atomic_write_text(&path, &format!("{raw}\n"), Some(0o600))
        .map_err(|error| format!("could not save SMB configuration: {error}"))?;
    Ok(())
}

#[tauri::command]
fn smb_configured_shares() -> Vec<SmbConfiguredShare> {
    load_smb_configured_shares()
}

#[tauri::command]
fn smb_save_configured_share(share: SmbConfiguredShare) -> Result<SmbActionResult, String> {
    if !valid_smb_configured_share(&share) {
        return Err("invalid SMB share configuration".to_string());
    }
    let mut shares = load_smb_configured_shares();
    shares.retain(|existing| existing.name != share.name);
    shares.push(share);
    save_smb_configured_shares(&shares)?;
    Ok(SmbActionResult {
        state: "complete".into(),
        detail: "Network share configuration saved.".into(),
    })
}

#[tauri::command]
fn smb_remove_configured_share(name: String) -> Result<SmbActionResult, String> {
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
    save_smb_configured_shares(&shares)?;
    Ok(SmbActionResult {
        state: "complete".into(),
        detail: "Network share configuration removed.".into(),
    })
}

#[derive(serde::Serialize)]
struct SmbActionResult {
    state: String,
    detail: String,
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
    // Remote names become part of the rclone `name:` positional, so restrict
    // them to alphanumerics, dash, and underscore (max 64) and reject a
    // leading dash that could parse as a flag.
    let valid_remote_name = !name.is_empty()
        && name.len() <= 64
        && !name.starts_with('-')
        && name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'));
    if !valid_remote_name {
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
fn cloud_sync_now(remote: String) -> Result<String, String> {
    let config_path = cloud_sync_config_path()?;
    let metadata = fs::symlink_metadata(&config_path)
        .map_err(|_| "Cloud sync is not configured yet".to_string())?;
    if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() > 128 * 1024 {
        return Err("Cloud sync configuration is unavailable".to_string());
    }
    let raw = fs::read_to_string(&config_path)
        .map_err(|_| "Could not read cloud sync configuration".to_string())?;
    let entries = serde_json::from_str::<HashMap<String, serde_json::Value>>(&raw)
        .map_err(|_| "Cloud sync configuration is invalid".to_string())?;
    let info = entries
        .get(&remote)
        .ok_or_else(|| "That cloud remote is not configured".to_string())?;
    let Some(configured) = valid_cloud_sync_remote(&remote, info) else {
        return Err("That cloud remote is invalid".to_string());
    };
    // The folder comes from a user-writable JSON file, so canonicalize it
    // and require it to stay under HOME before it becomes an rclone target.
    let home = std::env::var_os("HOME")
        .ok_or_else(|| "could not locate the current user's home directory".to_string())?;
    let home_path = PathBuf::from(&home);
    let home_canonical = fs::canonicalize(&home_path).unwrap_or(home_path.clone());
    let folder_path = PathBuf::from(&configured.folder);
    let folder_canonical = fs::canonicalize(&folder_path).unwrap_or_else(|_| {
        // The leaf may not exist yet, but its PARENTS might be symlinks
        // (`~/link-to-/data/new`): lexical cleaning alone never resolves
        // those, so the starts_with check below passes while rclone writes
        // outside HOME. Walk up to the nearest existing ancestor,
        // canonicalize THAT, then re-append the remainder.
        let absolute = if folder_path.is_absolute() {
            folder_path.clone()
        } else {
            home_canonical.join(&folder_path)
        };
        let mut existing = absolute.clone();
        let mut rest: Vec<std::ffi::OsString> = Vec::new();
        while !existing.exists() {
            match existing.file_name() {
                Some(name) => {
                    rest.push(name.to_os_string());
                    existing.pop();
                }
                None => break,
            }
        }
        let mut clean = fs::canonicalize(&existing).unwrap_or(existing);
        for component in rest.into_iter().rev() {
            if component == ".." {
                clean.pop();
            } else if component != "." {
                clean.push(component);
            }
        }
        clean
    });
    if !folder_canonical.starts_with(&home_canonical) {
        return Err("That cloud remote is invalid".to_string());
    }
    let folder = folder_canonical.to_string_lossy().into_owned();
    let job = commands::job::start_job("cloud-sync", &format!("Syncing {}…", configured.name))?;
    // `copy`, never `sync`: sync deletes local-only files to mirror the
    // remote, and a green "synced" after deleting saves is data loss.
    // Overwritten files go to a backup dir. rclone skips the backup dir
    // as a transfer target but still SCANS it — without this exclude,
    // displaced files pile up inside the user's folder on every run, and
    // would be resurrected as live files if the folder is ever synced back
    // as a source.
    let argv = vec![
        "rclone".to_string(),
        "copy".to_string(),
        "--progress".to_string(),
        "--stats-one-line".to_string(),
        "--stats=2s".to_string(),
        "--backup-dir".to_string(),
        format!("{folder}/.kyth-cloud-backup"),
        "--exclude".to_string(),
        "/.kyth-cloud-backup/**".to_string(),
        "--".to_string(),
        format!("{}:", configured.name),
        folder.clone(),
    ];
    commands::job::spawn_argv_job(
        job.clone(),
        argv,
        timeout_for(JobTimeoutClass::LongTransfer),
        move |result| match result {
            Ok(output) if output.status.success() => (
                "complete".to_string(),
                format!("{} synced to {}.", configured.name, folder),
            ),
            Ok(output) => (
                "failed".to_string(),
                commands::job::failure_detail("Cloud sync", &output),
            ),
            Err(error) => (
                "failed".to_string(),
                format!("Could not start cloud sync: {error}"),
            ),
        },
    );
    Ok(job)
}

#[tauri::command]
fn open_backup_app() -> Result<String, String> {
    // A detached `flatpak run` of a missing app fails where nobody reads
    // it — same precheck as sec_host_tool_launch, so a fresh install gets
    // an install pointer instead of a success toast and no window.
    if !kyth_shared::system::software_catalog::is_flatpak_installed("org.gnome.World.PikaBackup") {
        return Err(
            "Pika Backup is not installed; install it from the App Store first.".to_string(),
        );
    }
    kyth_shared::system::process::spawn_detached(
        std::process::Command::new("flatpak").args(["run", "org.gnome.World.PikaBackup"]),
    )
    .map_err(|error| format!("could not open Pika Backup: {error}"))?;
    Ok("Opened Pika Backup.".to_string())
}

#[tauri::command]
fn open_cloud_storage_app() -> Result<String, String> {
    kyth_shared::system::process::spawn_detached(
        std::process::Command::new("/usr/bin/kyth-welcome-launch")
            .args(["--page", "Cloud Storage"]),
    )
    .map_err(|error| format!("could not open Cloud Storage: {error}"))?;
    Ok("Opened the full Cloud Storage workflow.".to_string())
}

fn m365_app(name: &str) -> Option<(&'static str, &'static str)> {
    match name {
        "Outlook" => Some(("https://outlook.office.com/mail/", "Email and calendar")),
        "Word" => Some(("https://office.live.com/start/Word.aspx", "Documents")),
        "Excel" => Some(("https://office.live.com/start/Excel.aspx", "Spreadsheets")),
        "PowerPoint" => Some((
            "https://office.live.com/start/PowerPoint.aspx",
            "Presentations",
        )),
        "OneNote" => Some(("https://www.onenote.com/notebooks", "Notes")),
        "Teams" => Some(("https://teams.microsoft.com/", "Chat and meetings")),
        _ => None,
    }
}

#[tauri::command]
fn open_m365_app(name: String) -> Result<String, String> {
    let (url, _) = m365_app(&name).ok_or_else(|| "unknown Microsoft 365 app".to_string())?;
    kyth_shared::system::process::spawn_detached(std::process::Command::new("xdg-open").arg(url))
        .map_err(|error| format!("could not open {name}: {error}"))?;
    Ok(format!("Opened {name}."))
}

#[tauri::command]
fn create_m365_shortcuts() -> Result<String, String> {
    let home = std::env::var_os("HOME").ok_or_else(|| "HOME is not set".to_string())?;
    let directory = PathBuf::from(home).join(".local/share/applications");
    fs::create_dir_all(&directory)
        .map_err(|error| format!("could not create application directory: {error}"))?;
    let mut written = 0;
    for name in ["Outlook", "Word", "Excel", "PowerPoint", "OneNote", "Teams"] {
        let (url, comment) = m365_app(name).expect("fixed M365 catalog");
        let path = directory.join(format!("kyth-m365-{}.desktop", name.to_lowercase()));
        if let Ok(metadata) = fs::symlink_metadata(&path) {
            if metadata.file_type().is_symlink() || !metadata.is_file() {
                continue;
            }
        }
        // create_new is the atomic guard: a link swapped in between the
        // metadata check above and this write would otherwise redirect
        // attacker-controlled .desktop content into an arbitrary user file.
        // create_new fails if anything already exists, so an existing real
        // file is left untouched and never overwritten.
        let entry = format!("[Desktop Entry]\nType=Application\nName={name} (Microsoft 365)\nComment={comment}\nExec=/usr/bin/xdg-open {url}\nIcon=internet-web-browser\nCategories=Office;\n");
        match OpenOptions::new().write(true).create_new(true).open(&path) {
            Ok(mut file) => {
                use std::io::Write;
                file.write_all(entry.as_bytes())
                    .map_err(|error| format!("could not write {name} shortcut: {error}"))?;
                written += 1;
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(error) => return Err(format!("could not write {name} shortcut: {error}")),
        }
    }
    Ok(format!(
        "Added {written} Microsoft 365 shortcut(s) to the application menu."
    ))
}

fn add_pst_paths(root: &Path, depth: usize, paths: &mut Vec<String>) {
    if depth > 5 || paths.len() >= 50 {
        return;
    }
    let Ok(entries) = fs::read_dir(root) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let Ok(metadata) = fs::symlink_metadata(&path) else {
            continue;
        };
        if metadata.file_type().is_symlink() {
            continue;
        }
        if metadata.is_file()
            && path
                .extension()
                .and_then(|ext| ext.to_str())
                .is_some_and(|ext| matches!(ext.to_ascii_lowercase().as_str(), "pst" | "ost"))
        {
            paths.push(path.to_string_lossy().into_owned());
        } else if metadata.is_dir() {
            add_pst_paths(&path, depth + 1, paths);
        }
    }
}

#[tauri::command]
fn pst_files() -> Vec<String> {
    let Some(home) = std::env::var_os("HOME").map(PathBuf::from) else {
        return Vec::new();
    };
    let mut paths = Vec::new();
    let mut roots = vec![
        home.join("Documents"),
        home.join("Downloads"),
        home.join(".local/share"),
    ];
    if let Some(user) = std::env::var_os("USER") {
        roots.push(PathBuf::from("/run/media").join(user));
    }
    for root in roots.into_iter().filter(|path| path.is_dir()) {
        add_pst_paths(&root, 0, &mut paths);
    }
    paths.sort();
    paths.dedup();
    paths
}

fn allowed_pst_path(path: &str) -> Result<PathBuf, String> {
    let candidate = PathBuf::from(path);
    let canonical = candidate
        .canonicalize()
        .map_err(|_| "Outlook archive was not found".to_string())?;
    if !canonical.is_file()
        || !canonical
            .extension()
            .and_then(|ext| ext.to_str())
            .is_some_and(|ext| matches!(ext.to_ascii_lowercase().as_str(), "pst" | "ost"))
    {
        return Err("Only an existing .pst or .ost archive can be imported".to_string());
    }
    let home =
        PathBuf::from(std::env::var_os("HOME").ok_or_else(|| "HOME is not set".to_string())?);
    let mut allowed = vec![
        home.join("Documents"),
        home.join("Downloads"),
        home.join(".local/share"),
    ];
    if let Some(user) = std::env::var_os("USER") {
        allowed.push(PathBuf::from("/run/media").join(user));
    }
    // Canonicalize the roots too: comparing a canonical file against a
    // non-canonical root rejects legit files when the folder itself is a
    // symlink (e.g. ~/Documents -> /data/docs). Roots that cannot be
    // canonicalized (missing dir) are skipped, matching pst_files.
    let canonical_roots: Vec<PathBuf> = allowed
        .iter()
        .filter_map(|root| root.canonicalize().ok())
        .collect();
    if canonical_roots
        .iter()
        .any(|root| canonical.starts_with(root))
    {
        Ok(canonical)
    } else {
        Err("Archive must be in a user-owned migration folder".to_string())
    }
}

#[tauri::command]
fn convert_pst(path: String) -> Result<String, String> {
    let source = allowed_pst_path(&path)?;
    if !Path::new("/usr/bin/readpst").exists() && !Path::new("/bin/readpst").exists() {
        return Err(
            "readpst is not installed — install it before importing Outlook archives.".to_string(),
        );
    }
    let home =
        PathBuf::from(std::env::var_os("HOME").ok_or_else(|| "HOME is not set".to_string())?);
    let destination = home.join("Documents/Outlook Import");
    fs::create_dir_all(&destination)
        .map_err(|error| format!("could not create import folder: {error}"))?;
    let job = commands::job::start_job("pst", "Converting Outlook archive…")?;
    // Re-verify containment at use time: the check above and this spawn are
    // not atomic, and a link swapped in between would redirect the read.
    // The path is already canonical, so this re-check is idempotent.
    let source = allowed_pst_path(&source.to_string_lossy())?;
    let argv = vec![
        "readpst".to_string(),
        "-r".to_string(),
        "-o".to_string(),
        destination.to_string_lossy().into_owned(),
        source.to_string_lossy().into_owned(),
    ];
    commands::job::spawn_argv_job(
        job.clone(),
        argv,
        timeout_for(JobTimeoutClass::ExtendedWork),
        |result| match result {
            Ok(output) if output.status.success() => (
                "complete".to_string(),
                "Outlook archive converted to Documents/Outlook Import.".to_string(),
            ),
            Ok(output) => (
                "failed".to_string(),
                commands::job::failure_detail("Outlook import", &output),
            ),
            Err(error) => (
                "failed".to_string(),
                format!("Could not start Outlook import: {error}"),
            ),
        },
    );
    Ok(job)
}

#[tauri::command]
fn focus_start(minutes: u32) -> Result<String, String> {
    if !(1..=240).contains(&minutes) {
        return Err("Focus session must be between 1 and 240 minutes".to_string());
    }
    let mut sessions = focus_sessions()
        .lock()
        .map_err(|_| "focus session store is unavailable".to_string())?;
    // Reap sessions whose `sleep` already exited without a focus_stop call:
    // otherwise every unstopped session leaks a map entry (and an unwaited
    // child) for the life of the Hub process.
    sessions.retain(|_, existing| match existing.try_wait() {
        Ok(None) => true,
        Ok(Some(_)) => false,
        Err(error) => {
            eprintln!("focus: could not inspect inhibitor process: {error}");
            true
        }
    });
    // Kill inhibitors orphaned by a previous Hub process (crash/restart
    // reparents the `sleep` child, which then holds idle:sleep with no UI
    // to cancel it). Live sessions in this process are spared.
    let live_pids: Vec<u32> = sessions.values().map(|child| child.id()).collect();
    drop(sessions);
    let orphans = kyth_shared::system::process::reap_stale_focus_inhibits(&live_pids);
    if orphans > 0 {
        eprintln!(
            "focus: reaped {orphans} orphaned sleep inhibitor(s) from a previous Hub process"
        );
    }
    let child = std::process::Command::new("systemd-inhibit")
        .args([
            "--what=idle:sleep",
            "--why=KythOS Focus Session",
            "--mode=block",
            "sleep",
            &(minutes * 60 + 60).to_string(),
        ])
        .spawn()
        .map_err(|error| format!("could not keep the PC awake: {error}"))?;
    let id = format!(
        "focus-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    let mut sessions = focus_sessions()
        .lock()
        .map_err(|_| "focus session store is unavailable".to_string())?;
    sessions.insert(id.clone(), child);
    Ok(id)
}

#[tauri::command]
fn focus_stop(id: String) -> Result<String, String> {
    let mut sessions = focus_sessions()
        .lock()
        .map_err(|_| "focus session store is unavailable".to_string())?;
    let Some(mut child) = sessions.remove(&id) else {
        return Ok("Focus session already ended.".to_string());
    };
    drop(sessions);
    // Never block the command on an unwaited child: TERM the process,
    // SIGKILL its group for good measure (harmless ESRCH when the child
    // is not a group leader), then give it 2s to exit before reaping.
    kyth_shared::system::process::kill_process_group(&mut child);
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(2);
    loop {
        match child.try_wait() {
            Ok(Some(_)) => break,
            Ok(None) if std::time::Instant::now() < deadline => {
                std::thread::sleep(std::time::Duration::from_millis(25));
            }
            _ => {
                kyth_shared::system::process::kill_process_group(&mut child);
                let _ = child.wait();
                break;
            }
        }
    }
    Ok("Focus session ended; normal power behavior is restored.".to_string())
}

#[tauri::command]
fn open_move_files_app() -> Result<String, String> {
    kyth_shared::system::process::spawn_detached(
        std::process::Command::new("/usr/bin/kyth-welcome-launch").args(["--page", "Move Files"]),
    )
    .map_err(|error| format!("could not open Move Files: {error}"))?;
    Ok("Opened the full Windows migration workflow.".to_string())
}

#[tauri::command]
fn open_network_shares_app() -> Result<String, String> {
    kyth_shared::system::process::spawn_detached(
        std::process::Command::new("/usr/bin/kyth-welcome-launch")
            .args(["--page", "Network Shares"]),
    )
    .map_err(|error| format!("could not open Network Shares: {error}"))?;
    Ok("Opened the full Network Shares workflow.".to_string())
}
#[tauri::command]
fn ipp_discover() -> Vec<String> {
    kyth_shared::system::printing::ipp_discover()
}
#[derive(serde::Serialize)]
struct BtrfsHealthResponse {
    status: String,
    detail: String,
}
#[tauri::command]
async fn btrfs_health() -> BtrfsHealthResponse {
    tauri::async_runtime::spawn_blocking(|| {
        let (status, detail) = kyth_shared::system::btrfs_status::btrfs_health_summary();
        BtrfsHealthResponse { status, detail }
    })
    .await
    .unwrap_or(BtrfsHealthResponse {
        status: "unknown".to_string(),
        detail: "Btrfs health could not be read.".to_string(),
    })
}
#[tauri::command]
async fn loaded_kernel_modules() -> Vec<String> {
    tauri::async_runtime::spawn_blocking(|| {
        kyth_shared::system::drivers::get_loaded_kernel_modules()
            .into_iter()
            .collect()
    })
    .await
    .unwrap_or_default()
}
#[tauri::command]
async fn pci_devices_by_class(class: String) -> Vec<String> {
    tauri::async_runtime::spawn_blocking(move || {
        kyth_shared::system::drivers::get_pci_devices_by_class(&class)
    })
    .await
    .unwrap_or_default()
}

#[tauri::command]
async fn controllers_detect() -> ControllersDetectResponse {
    tauri::async_runtime::spawn_blocking(|| {
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
    })
    .await
    .unwrap_or(ControllersDetectResponse {
        usb_controllers: Vec::new(),
        input_nodes: Vec::new(),
        xone_dongle: false,
        xone_loaded: false,
        xpadneo_loaded: false,
        hid_ps_loaded: false,
        dualsense_found: false,
    })
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
async fn network_identity() -> NetworkIdentityResponse {
    tauri::async_runtime::spawn_blocking(|| {
        let n = kyth_shared::system::network_identity::get_network_identity();
        NetworkIdentityResponse {
            vpn_connected: n.vpn_connected,
            vpn_name: n.vpn_name,
            smb_mounts: n.smb_mounts,
            cloud_providers: n.cloud_providers,
            detail: n.detail,
        }
    })
    .await
    .unwrap_or(NetworkIdentityResponse {
        vpn_connected: false,
        vpn_name: String::new(),
        smb_mounts: 0,
        cloud_providers: Vec::new(),
        detail: "Network status could not be read.".to_string(),
    })
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
async fn installed_flatpaks() -> Vec<kyth_shared::system::software_catalog::InstalledFlatpak> {
    tauri::async_runtime::spawn_blocking(kyth_shared::system::software_catalog::installed_flatpaks)
        .await
        .unwrap_or_default()
}

#[tauri::command]
fn uninstall_flatpak(app_id: String) -> Result<InstallActionLaunch, String> {
    commands::privilege::validate_flatpak_id(&app_id)?;
    let job = format!(
        "flatpak-uninstall-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    let pending_detail = format!("Uninstalling {app_id}…");
    let (job, cancel) = app_installs().start(&job, pending_detail.clone());
    let job_for_thread = job.clone();
    std::thread::spawn(move || {
        // Resolve scope inside the worker: the full `flatpak list` scan
        // blocks, so doing it on the command thread hitches the UI, and a
        // scope read up front can go stale before the worker acts on it.
        let scope = kyth_shared::system::software_catalog::installed_flatpaks()
            .into_iter()
            .find(|app| app.id == app_id)
            .map(|app| app.scope);
        let Some(scope) = scope else {
            app_installs().finish(
                &job_for_thread,
                "failed",
                "That Flatpak is not installed.".to_string(),
            );
            return;
        };
        let result: Result<(bool, String), String> = if scope == "system" {
            privileged_flatpak_uninstall(&app_id).map(|detail| (true, detail))
        } else {
            // A stalled mirror must surface as a timeout, not a forever
            // "running" job: bound like every other Hub recipe action.
            let mut command = std::process::Command::new("flatpak");
            command.args(["uninstall", "--user", "-y", &app_id]);
            kyth_shared::system::process::run_bounded_command_cancel(
                command,
                timeout_for(JobTimeoutClass::HubAction),
                &cancel,
            )
            .map(|output| {
                if output.status.success() {
                    (true, format!("Uninstalled {app_id}."))
                } else {
                    (false, commands::process::bounded_text(&output.stderr))
                }
            })
            .map_err(|err| err.to_string())
        };
        let (state, detail) = match result {
            Ok((true, detail)) => ("complete", detail),
            Ok((false, detail)) => ("failed", detail),
            Err(err) => ("failed", format!("Could not uninstall Flatpak: {err}")),
        };
        app_installs().finish(&job_for_thread, state, detail);
    });
    Ok(InstallActionLaunch {
        job,
        state: "running".into(),
        detail: pending_detail,
    })
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
    kyth_shared::system::process::spawn_detached(&mut std::process::Command::new(&path))
        .map(|_| "AppImage launched.".to_string())
        .map_err(|err| format!("could not launch AppImage: {err}"))
}

#[derive(serde::Serialize)]
pub(crate) struct InstallStatus {
    id: String,
    state: String,
    detail: String,
}

#[derive(serde::Serialize)]
pub(crate) struct InstallActionLaunch {
    job: String,
    state: String,
    detail: String,
}

#[tauri::command]
fn update_flatpaks() -> Result<InstallActionLaunch, String> {
    let job = format!(
        "flatpak-update-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    let pending_detail = "Updating your apps…".to_string();
    let (job, cancel) = app_installs().start(&job, pending_detail.clone());
    let job_for_thread = job.clone();
    std::thread::spawn(move || {
        let mut user_command = std::process::Command::new("flatpak");
        user_command.args(["update", "--user", "-y"]);
        // A stalled mirror must surface as a timeout, not a forever
        // "running" job; the tier matches the privileged daemon's own
        // flatpak bound (kyth-shared-rs/src/privileged.rs OPERATION_TIMEOUT).
        let user_result = match kyth_shared::system::process::run_bounded_command_cancel(
            user_command,
            timeout_for(JobTimeoutClass::HubAction),
            &cancel,
        ) {
            Ok(output) if output.status.success() => Ok(()),
            Ok(output) => Err(commands::process::bounded_text(&output.stderr)),
            Err(error) if error.kind() == std::io::ErrorKind::TimedOut => {
                Err("Updating your apps took too long and was stopped.".to_string())
            }
            Err(error) => Err(format!("Could not start Flatpak: {error}")),
        };
        // A cancel during the user phase must not fall through into system
        // mutations: the job is already marked cancelled, and finish() never
        // overwrites a cancelled job, so returning here is the whole fix.
        // (A cancel that lands mid-flight in phase 2 still waits for the
        // daemon's own bounded reply; the socket read cannot be preempted.)
        if cancel.load(std::sync::atomic::Ordering::Relaxed) {
            return;
        }
        let system_result = commands::privilege::flatpak_update().map(|_| ());
        let (state, detail) = match (user_result, system_result) {
            (Ok(()), Ok(())) => {
                let (remaining, verification_detail) =
                    kyth_shared::system::update_availability::flatpak_updates_count(false);
                match kyth_shared::system::update_availability::flatpak_update_completion(
                    remaining,
                    &verification_detail,
                ) {
                    Ok(detail) => ("complete", detail),
                    Err(detail) => ("failed", detail),
                }
            },
            (Err(user_error), Ok(())) => (
                "failed",
                format!("Your personal apps could not be updated: {user_error}"),
            ),
            (Ok(()), Err(system_error)) => (
                "failed",
                format!("Your personal apps were updated, but system-wide app updates need attention: {system_error}"),
            ),
            (Err(user_error), Err(system_error)) => (
                "failed",
                format!("Your apps could not be updated: {user_error}; system-wide updates: {system_error}"),
            ),
        };
        app_installs().finish(&job_for_thread, state, detail);
    });
    Ok(InstallActionLaunch {
        job,
        state: "running".into(),
        detail: pending_detail,
    })
}

#[tauri::command]
fn install_flatpak(app_id: String) -> Result<InstallActionLaunch, String> {
    commands::privilege::validate_flatpak_id(&app_id)?;
    let job = format!(
        "flatpak-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    let pending_detail = format!("Installing {app_id}…");
    let (job, cancel) = app_installs().start(&job, pending_detail.clone());
    let job_for_thread = job.clone();
    std::thread::spawn(move || {
        // Unbounded `.output()` hangs on a stalled mirror with no way to
        // cancel; run bounded and cancellable like the other install paths.
        let mut command = std::process::Command::new("flatpak");
        command.args(["install", "--user", "-y", "flathub", &app_id]);
        let result = kyth_shared::system::process::run_bounded_command_cancel(
            command,
            timeout_for(JobTimeoutClass::HubAction),
            &cancel,
        );
        let (state, detail) = match result {
            Ok(output) if output.status.success() => {
                ("complete", "Installation complete.".to_string())
            }
            Ok(output) => ("failed", commands::process::bounded_text(&output.stderr)),
            Err(err) => ("failed", format!("Could not start Flatpak: {err}")),
        };
        app_installs().finish(&job_for_thread, state, detail);
    });
    Ok(InstallActionLaunch {
        job,
        state: "running".into(),
        detail: pending_detail,
    })
}

#[tauri::command]
fn install_status(job: String) -> InstallStatus {
    let (state, detail) = app_installs().status(&job).unwrap_or((
        kyth_shared::system::jobs::STATE_UNKNOWN.into(),
        "Installation job not found.".into(),
    ));
    InstallStatus {
        id: job,
        state,
        detail,
    }
}

/// Cancel a running install job: its process is killed within one poll tick
/// and the job reads `cancelled` from then on.
#[tauri::command]
fn install_cancel(job: String) -> InstallStatus {
    app_installs().cancel(&job);
    install_status(job)
}

#[tauri::command]
async fn protondb_lookup_many(
    app_ids: Vec<String>,
) -> Vec<kyth_shared::system::gaming_compat::ProtonDbResult> {
    tauri::async_runtime::spawn_blocking(move || {
        kyth_shared::system::gaming_compat::protondb_lookup_many(&app_ids)
    })
    .await
    .unwrap_or_default()
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
    const BUNDLED: &str = include_str!("../../src/data/compat_games.json");
    serde_json::from_str::<CompatibilityBundle>(BUNDLED)
        .map(|bundle| bundle.games)
        .unwrap_or_default()
}

#[tauri::command]
async fn telemetry_recent(limit: Option<u32>) -> Vec<kyth_shared::system::telemetry::SessionRow> {
    // The webview supplies the limit; clamp it so a crafted value cannot
    // turn a small chart query into a full-table dump.
    let limit = limit.unwrap_or(15).min(200) as usize;
    tauri::async_runtime::spawn_blocking(move || {
        kyth_shared::system::telemetry::recent_sessions(limit)
    })
    .await
    .unwrap_or_default()
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
    let home = std::env::var_os("HOME")
        .map(std::path::PathBuf::from)
        .unwrap_or_default();
    kyth_shared::system::windows_verify::verify(home, std::path::Path::new("/var/home").exists())
}

/// A profile summary contains no password, cookie, or SAML material.
#[derive(Serialize)]
struct VpnSavedProfile {
    gateway: String,
    protocol: String,
    os: String,
}

fn valid_vpn_profile_text(value: &str, maximum: usize) -> bool {
    !value.is_empty() && value.len() <= maximum && !value.chars().any(char::is_control)
}

#[tauri::command]
fn vpn_saved_profile() -> Option<VpnSavedProfile> {
    let home = std::env::var_os("HOME")?;
    let path = PathBuf::from(home).join(".config/kyth-vpn-connect");
    let metadata = fs::symlink_metadata(&path).ok()?;
    if !metadata.is_file() || metadata.len() > 16 * 1024 {
        return None;
    }
    let raw = fs::read_to_string(path).ok()?;
    let mut in_vpn_section = false;
    let mut values = HashMap::new();
    for line in raw.lines() {
        let line = line.trim();
        if line.starts_with('[') && line.ends_with(']') {
            in_vpn_section = line.eq_ignore_ascii_case("[vpn]");
            continue;
        }
        if !in_vpn_section || line.starts_with('#') || line.starts_with(';') {
            continue;
        }
        // One hand-edited or legacy line without '=' must not erase the
        // whole saved profile (and force re-entering gateway/creds): skip
        // it, keep the keys that did parse.
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        values.insert(key.trim().to_ascii_lowercase(), value.trim().to_string());
    }
    let gateway = values.remove("gateway")?;
    let protocol = values.remove("protocol")?;
    let os = values.remove("os")?;
    if !valid_vpn_profile_text(&gateway, 253)
        || !matches!(
            protocol.as_str(),
            "gp" | "anyconnect" | "pulse" | "nc" | "f5" | "fortinet" | "array"
        )
        || !matches!(os.as_str(), "win" | "linux" | "mac")
    {
        return None;
    }
    Some(VpnSavedProfile {
        gateway,
        protocol,
        os,
    })
}

#[tauri::command]
async fn desktop_stack_checks() -> Vec<kyth_shared::system::desktop_stack::StackCheck> {
    tauri::async_runtime::spawn_blocking(kyth_shared::system::desktop_stack::desktop_stack_checks)
        .await
        .unwrap_or_default()
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
    kyth_shared::system::process::spawn_detached(std::process::Command::new("xdg-open").arg(&url))
        .map_err(|err| format!("could not open browser: {err}"))?;
    Ok("Opened a prefilled issue in your browser.".to_string())
}

/// One-shot pull for the page this process was launched with (`--page`,
/// e.g. from a desktop file or CLI deep link). Pulled by the frontend on
/// mount rather than pushed as an event, to avoid a race against the
/// webview's JS not having registered its "navigate" listener yet.
#[tauri::command]
fn take_pending_page(state: tauri::State<PendingPage>) -> Option<String> {
    state.0.lock().ok().and_then(|mut pending| pending.take())
}

#[derive(Serialize)]
struct ExeHandlerInspection {
    path: String,
    basename: String,
    is_rpm: bool,
    app_name: Option<String>,
    suggestion: String,
    flatpak_id: Option<String>,
    search_term: String,
    compatibility: Option<kyth_shared::system::windows_installer::CompatibilityAssessment>,
    sha256_prefix: Option<String>,
    sha256_full: Option<String>,
    trusted_direct: bool,
    auto_bottles: bool,
}

fn home_trusted(sha256: &str) -> bool {
    std::env::var_os("HOME")
        .map(std::path::PathBuf::from)
        .and_then(|home| kyth_shared::system::exe_trust::trusted_runner(&home, sha256))
        .is_some()
}

fn exe_handler_config_path() -> PathBuf {
    std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".config")))
        .unwrap_or_else(|| PathBuf::from(".config"))
        .join("kyth/exe-handler.conf")
}

fn load_auto_bottles() -> bool {
    let Ok(text) = fs::read_to_string(exe_handler_config_path()) else {
        return false;
    };
    let mut in_section = false;
    for line in text.lines() {
        let line = line.trim();
        if line.starts_with('[') && line.ends_with(']') {
            in_section = line == "[exe-handler]";
        } else if in_section
            && line.split_once('=').is_some_and(|(key, value)| {
                key.trim() == "auto_bottles" && value.trim().eq_ignore_ascii_case("true")
            })
        {
            return true;
        }
    }
    false
}

fn regular_handler_path(path: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(path);
    let metadata = fs::symlink_metadata(&path)
        .map_err(|error| format!("The installer could not be read: {error}"))?;
    if metadata.file_type().is_symlink() || !metadata.file_type().is_file() {
        return Err("Choose a regular, non-symbolic-link installer file.".into());
    }
    path.canonicalize()
        .map_err(|error| format!("The installer could not be read: {error}"))
}

#[tauri::command]
fn exe_handler_inspect(path: String) -> Result<ExeHandlerInspection, String> {
    let path = regular_handler_path(&path)?;
    let basename = path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("installer")
        .to_string();
    let is_rpm = kyth_shared::system::app_suggestions::is_rpm_installer(&basename);
    if is_rpm {
        return Ok(ExeHandlerInspection {
            path: path.display().to_string(), basename: basename.clone(), is_rpm: true,
            app_name: Some("RPM Package".into()),
            suggestion: "This is an RPM package for traditional mutable Fedora/RHEL-style systems. On KythOS, install desktop apps from App Store or Flathub. Use Distrobox for command-line tools that need dnf. Only layer system RPMs when a KythOS guide explicitly tells you to, because base-system changes require a reboot and can complicate updates.".into(),
            flatpak_id: None, search_term: basename.trim_end_matches(".rpm").replace(' ', "+"), compatibility: None, sha256_prefix: None, sha256_full: None, trusted_direct: false, auto_bottles: false,
        });
    }
    let request = kyth_shared::system::windows_installer::inspect_installer(&path)
        .map_err(|error| error.message)?;
    let suggestion = kyth_shared::system::app_suggestions::suggest_default(
        &kyth_shared::system::app_suggestions::normalise_filename(&basename),
    );
    let app_name = suggestion.as_ref().map(|entry| entry.app_name.clone());
    let search_term = app_name
        .clone()
        .unwrap_or_else(|| {
            path.file_stem()
                .and_then(|stem| stem.to_str())
                .unwrap_or("Windows Application")
                .to_string()
        })
        .replace(' ', "+");
    Ok(ExeHandlerInspection {
        path: path.display().to_string(), basename, is_rpm: false,
        suggestion: suggestion.as_ref().map(|entry| entry.suggestion.clone()).unwrap_or_else(|| "This is a Windows application installer. KythOS runs Linux software natively. Search Flathub for a Linux equivalent, or run it inside Bottles (Wine).".into()),
        flatpak_id: suggestion.and_then(|entry| entry.flatpak_id), app_name, search_term,
        compatibility: Some(kyth_shared::system::windows_installer::assess_compatibility(&request)),
        sha256_prefix: Some(request.sha256[..16].to_string()), sha256_full: Some(request.sha256.clone()), trusted_direct: home_trusted(&request.sha256), auto_bottles: load_auto_bottles(),
    })
}

/// Record trust-once consent: this exact file content (full SHA-256)
/// launches straight into `runner` on future double-clicks with no dialog.
/// The hash gates everything — a modified file falls back to the dialog.
#[tauri::command]
fn exe_handler_trust(sha256: String, name: String, runner: String) -> Result<(), String> {
    let home = std::env::var_os("HOME")
        .map(std::path::PathBuf::from)
        .ok_or("could not determine the home directory")?;
    kyth_shared::system::exe_trust::trust_file(&home, &sha256, &name, &runner)
}

/// Drop trust-once consent for one hash. Missing entries succeed silently.
#[tauri::command]
fn exe_handler_untrust(sha256: String) -> Result<(), String> {
    let home = std::env::var_os("HOME")
        .map(std::path::PathBuf::from)
        .ok_or("could not determine the home directory")?;
    kyth_shared::system::exe_trust::untrust_file(&home, &sha256)
}

/// Launch a trusted-or-dialog-approved game executable via umu+Proton.
/// Fire-and-forget: the game outlives the Hub like a natively launched app.
#[tauri::command]
fn exe_handler_launch_umu(path: String) -> Result<(), String> {
    let path = regular_handler_path(&path)?;
    kyth_shared::system::windows_installer::launch_in_umu(&path)
}

/// First-boot app status for the Play checklist: whether the background
/// Steam install is still running, ready, or needs attention.
#[derive(serde::Serialize)]
struct FirstbootAppsStatus {
    state: String,
    message: String,
    updated: String,
}

/// Steam Play default status for the Play checklist (read-only VDF scan).
#[derive(serde::Serialize)]
struct SteamPlayStatusFront {
    steam_present: bool,
    steam_running: bool,
    mapping_present: bool,
    detail: String,
}

#[tauri::command]
fn steam_play_status() -> SteamPlayStatusFront {
    let home = std::env::var_os("HOME").map(std::path::PathBuf::from);
    let blank = || SteamPlayStatusFront {
        steam_present: false,
        steam_running: false,
        mapping_present: false,
        detail: "No home directory.".to_string(),
    };
    home.as_deref()
        .map(|root| {
            let status = kyth_shared::system::gaming_compat::steam_play_status(root);
            SteamPlayStatusFront {
                steam_present: status.steam_present,
                steam_running: status.steam_running,
                mapping_present: status.mapping_present,
                detail: status.detail,
            }
        })
        .unwrap_or_else(blank)
}

#[tauri::command]
fn firstboot_apps_status() -> FirstbootAppsStatus {
    let home = std::env::var_os("HOME").map(std::path::PathBuf::from);
    let (state, message, updated) = home
        .as_deref()
        .map(kyth_shared::system::firstboot::read_app_status)
        .unwrap_or_else(|| ("unknown".to_string(), String::new(), String::new()));
    FirstbootAppsStatus {
        state,
        message,
        updated,
    }
}

#[tauri::command]
fn exe_handler_set_auto_bottles(enabled: bool) -> Result<(), String> {
    let path = exe_handler_config_path();
    let directory = path.parent().ok_or("invalid Kyth configuration path")?;
    fs::create_dir_all(directory).map_err(|error| format!("Could not save preference: {error}"))?;
    // Parse-modify-write, preserving every other key/section: a bare
    // fs::write of the two known lines would discard anything else a user
    // or a future version stores here. Atomic temp + fsync + rename so a
    // crash mid-write never leaves a truncated file.
    let desired = format!("auto_bottles={}", if enabled { "true" } else { "false" });
    let mut lines: Vec<String> = match fs::read_to_string(&path) {
        Ok(text) => text.lines().map(str::to_string).collect(),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Vec::new(),
        Err(error) => return Err(format!("Could not save preference: {error}")),
    };
    let mut in_section = false;
    let mut section_seen = false;
    let mut key_written = false;
    for line in &mut lines {
        let trimmed = line.trim();
        if trimmed.starts_with('[') && trimmed.ends_with(']') {
            in_section = trimmed == "[exe-handler]";
            section_seen = section_seen || in_section;
        } else if in_section
            && trimmed
                .split_once('=')
                .is_some_and(|(key, _)| key.trim() == "auto_bottles")
        {
            *line = desired.clone();
            key_written = true;
        }
    }
    if !key_written {
        if !section_seen {
            lines.push("[exe-handler]".to_string());
        }
        lines.push(desired);
    }
    let mut rendered = lines.join("\n");
    rendered.push('\n');
    kyth_shared::atomic_io::atomic_write_text(&path, &rendered, Some(0o600))
        .map_err(|error| format!("Could not save preference: {error}"))
}

#[tauri::command]
fn exe_handler_open_flathub(search_term: String) -> Result<(), String> {
    let query: String = url::form_urlencoded::byte_serialize(search_term.as_bytes()).collect();
    let mut open = Command::new("xdg-open");
    open.arg(format!("https://flathub.org/apps/search?q={query}"))
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    kyth_shared::system::process::spawn_detached(&mut open)
        .map(|_| ())
        .map_err(|error| format!("Could not open Flathub: {error}"))
}

#[tauri::command]
fn exe_handler_flatpak_installed(app_id: String) -> Result<bool, String> {
    commands::privilege::validate_flatpak_id(&app_id)?;
    // Bounded lookup: a bare `status()` blocks this command for as long
    // as flatpak hangs. Any failure (timeout, missing binary) reads as
    // "not installed" for the UI rather than an error.
    match kyth_shared::system::process::run_bounded(
        &[
            "flatpak".to_string(),
            "info".to_string(),
            "--user".to_string(),
            app_id,
        ],
        std::time::Duration::from_secs(15),
    ) {
        Ok(output) => Ok(output.status.success()),
        Err(_) => Ok(false),
    }
}

#[tauri::command]
fn exe_handler_launch_flatpak(app_id: String) -> Result<(), String> {
    commands::privilege::validate_flatpak_id(&app_id)?;
    if !kyth_shared::system::software_catalog::is_flatpak_installed(&app_id) {
        return Err("That Linux application is not installed.".to_string());
    }
    let mut run = Command::new("flatpak");
    run.args(["run", "--user", &app_id])
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    kyth_shared::system::process::spawn_detached(&mut run)
        .map(|_| ())
        .map_err(|error| format!("Could not launch the Linux application: {error}"))
}

#[tauri::command]
fn exe_handler_start_bottles(
    path: String,
    allow_unsupported: bool,
) -> Result<InstallActionLaunch, String> {
    let request =
        kyth_shared::system::windows_installer::inspect_installer(regular_handler_path(&path)?)
            .map_err(|error| error.message)?;
    if matches!(
        kyth_shared::system::windows_installer::assess_compatibility(&request).level,
        kyth_shared::system::windows_installer::Compatibility::Unsupported
    ) && !allow_unsupported
    {
        return Err(
            "This installer has a known limitation. Confirm before trying it anyway.".into(),
        );
    }
    let job = format!(
        "exe-handler-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    let pending_detail = "Preparing an isolated Bottles environment…".to_string();
    // launch_in_bottles is a library call, not a child process: cancelling
    // marks the job and its late finish becomes a no-op.
    let (job, _) = app_installs().start(&job, pending_detail.clone());
    let job_for_thread = job.clone();
    std::thread::spawn(move || {
        let home = std::env::var_os("HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/tmp"));
        let (state, detail) =
            match kyth_shared::system::windows_installer::launch_in_bottles(&request, home) {
                Ok(_) => (
                    "complete",
                    "The Windows installer is opening in its isolated environment.".to_string(),
                ),
                Err(error) => ("failed", error.message),
            };
        app_installs().finish(&job_for_thread, state, detail);
    });
    Ok(InstallActionLaunch {
        job,
        state: "running".into(),
        detail: pending_detail,
    })
}

#[tauri::command]
fn take_pending_exe_handler(state: tauri::State<PendingExeHandler>) -> Option<String> {
    state.0.lock().ok().and_then(|mut pending| pending.take())
}

/// Append a small, opt-in record for the installed-image acceptance guest.
/// The command is inert on normal launches: the guest supplies the file path
/// through the environment and only then does the shell write evidence. Keep
/// the path constrained to /tmp because this is test telemetry, not a general
/// filesystem-write bridge.
#[tauri::command]
fn acceptance_record(event: String, detail: String) -> Result<(), String> {
    let Some(path) = std::env::var_os("KYTH_HUB_ACCEPTANCE_FILE") else {
        return Err("Hub acceptance telemetry is disabled".into());
    };
    let path = PathBuf::from(path);
    if !path.starts_with("/tmp/") {
        return Err("Hub acceptance telemetry path is outside /tmp".into());
    }
    if event.is_empty()
        || event.len() > 64
        || !event
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte == b'-')
    {
        return Err("invalid Hub acceptance event".into());
    }
    let detail = detail.replace(['\n', '\r'], " ");
    if detail.len() > 4096 {
        return Err("Hub acceptance detail is too long".into());
    }
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .mode(0o600)
        .open(path)
        .map_err(|error| format!("could not write Hub acceptance evidence: {error}"))?;
    writeln!(file, "KYTH_HUB_ACCEPTANCE:{event}:{detail}")
        .map_err(|error| format!("could not flush Hub acceptance evidence: {error}"))
}

#[tauri::command]
fn acceptance_mode() -> bool {
    std::env::var("KYTH_HUB_ACCEPTANCE_FILE").is_ok()
}

#[tauri::command]
fn acceptance_degraded_dashboard() -> bool {
    acceptance_mode() && std::env::var("KYTH_HUB_ACCEPTANCE_DEGRADED").as_deref() == Ok("1")
}

fn main() {
    let argv = std::env::args().collect::<Vec<_>>();
    let initial_page = extract_page_arg(&argv);
    let initial_exe_handler = extract_exe_handler_arg(&argv);

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, argv, _cwd| {
            // A second launch forwards here instead of opening a second
            // window — same "single instance, focus the existing one"
            // contract instance_ipc.py gives the current Qt Hub. Unlike
            // the initial-launch case, the webview is already up by now,
            // so this pushes the event directly instead of going through
            // PendingPage.
            let page = extract_page_arg(&argv);
            let exe_handler = extract_exe_handler_arg(&argv);
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
                if let Some(page) = page {
                    let _ = window.emit("navigate", page);
                }
                if let Some(path) = exe_handler {
                    let _ = window.emit("exe-handler", path);
                }
            }
        }))
        .manage(PendingPage(Mutex::new(initial_page)))
        .manage(PendingExeHandler(Mutex::new(initial_exe_handler)))
        .invoke_handler(tauri::generate_handler![
            commands::dashboard::probe_backend,
            guardian_snapshot,
            guardian_check,
            guardian_check_status,
            guardian_check_cancel,
            guardian_control,
            commands::privilege::privileged_action,
            commands::privilege::privileged_action_status,
            commands::privilege::privileged_action_cancel,
            acceptance_record,
            acceptance_mode,
            acceptance_degraded_dashboard,
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
            update_flatpaks,
            install_status,
            install_cancel,
            protondb_lookup_many,
            anti_cheat_table,
            compatibility_games,
            take_pending_page,
            take_pending_exe_handler,
            exe_handler_inspect,
            firstboot_apps_status,
            steam_play_status,
            exe_handler_trust,
            exe_handler_untrust,
            exe_handler_launch_umu,
            exe_handler_set_auto_bottles,
            exe_handler_open_flathub,
            exe_handler_flatpak_installed,
            exe_handler_launch_flatpak,
            exe_handler_start_bottles,
            commands::updates::just_list,
            commands::updates::run_hub_action,
            commands::updates::hub_action_status,
            commands::updates::hub_action_cancel,
            commands::updates::bootc_upgrade,
            commands::updates::stage_progress,
            commands::updates::bootc_rollback,
            commands::updates::bootc_switch_branch,
            guardian_execute_recipe,
            guardian_dismiss,
            commands::updates::branch_display_name,
            mok_status,
            fonts_ready,
            mesa_version,
            mesa_overlay_dry_run,
            smb_browse,
            smb_mount,
            smb_configured_shares,
            smb_save_configured_share,
            smb_remove_configured_share,
            memory_pressure,
            snapshot_count,
            snapshot_timeline,
            is_gaming_slice_available,
            cloud_oauth_status,
            cloud_sync_remotes,
            cloud_sync_now,
            open_cloud_storage_app,
            open_backup_app,
            open_move_files_app,
            open_network_shares_app,
            ipp_discover,
            btrfs_health,
            loaded_kernel_modules,
            pci_devices_by_class,
            controllers_detect,
            hardware_view_summary,
            network_identity,
            commands::updates::pending_updates_summary,
            available_audio_presets,
            apply_pipewire_quantum,
            deployment_history,
            commands::dashboard::recovery_status,
            commands::updates::update_status,
            commands::updates::update_release_summary,
            is_live_session,
            strip_ansi,
            disk_write_bytes,
            firmware_updates_count,
            plasma_presets,
            apply_plasma_preset,
            amd64_manifest_entry,
            commands::updates::collect_availability,
            ntfs_devices,
            migration_readiness,
            commands::vpn::open_vpn_app,
            commands::vpn::vpn_connect,
            commands::vpn::vpn_status,
            commands::vpn::vpn_disconnect,
            commands::vpn::vpn_protection_status,
            commands::vpn::set_vpn_protection,
            vpn_saved_profile,
            commands::dashboard::boot_runtime_checks,
            desktop_stack_checks,
            commands::dashboard::current_user_name,
            commands::updates::current_update_channel,
            open_feedback_issue,
            commands::security::kali_status,
            commands::security::kali_create,
            commands::security::kali_export,
            commands::security::kali_remove,
            commands::security::kali_enter_terminal,
            commands::security::security_job_status,
            commands::security::security_job_cancel,
            commands::security::sec_host_tools,
            commands::security::sec_host_tool_install,
            commands::security::sec_host_tool_uninstall,
            commands::security::sec_host_tool_launch,
            commands::gaming::gaming_tools,
            commands::gaming::gaming_tool_install,
            commands::gaming::gaming_tool_uninstall,
            commands::gaming::gaming_tool_launch,
            commands::gaming::gaming_job_status,
            commands::gaming::gaming_job_cancel,
            commands::gaming::fix_discord_screenshare,
            commands::gaming::fix_obs_pipewire,
            commands::gaming::open_game_folder,
            commands::gaming::gaming_perf_status,
            commands::gaming::scx_status,
            commands::gaming::scx_available,
            commands::gaming::scx_set_scheduler,
            commands::gaming::per_game_profile,
            commands::gaming::save_per_game_profile,
            commands::gaming::per_game_launch_options,
            commands::dev_tools::dev_tools_catalog_list,
            commands::dev_tools::ai_dev_box_status,
            commands::dev_tools::dev_tools_install_selection,
            commands::dev_tools::dev_tools_job_status,
            commands::dev_tools::dev_tools_job_cancel,
            commands::updates::apply_staged,
            commands::updates::update_job_status,
            commands::updates::update_job_cancel,
            commands::updates::update_health,
            commands::job::job_status,
            commands::job::cancel_job,
            open_m365_app,
            create_m365_shortcuts,
            pst_files,
            convert_pst,
            focus_start,
            focus_stop,
        ])
        .run(tauri::generate_context!())
        .expect("error while running the Kyth Hub shell");
}
