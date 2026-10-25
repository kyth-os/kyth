//! Security tab bridge: the Kali distrobox lifecycle (create/enter/export/
//! remove) and the host-side (Flatpak) security-tools grid. Command argv
//! comes entirely from `kyth_shared::system::security_container`'s fixed
//! templates/catalog — nothing here accepts a free-form command or Flatpak
//! id from the webview.
//!
//! Jobs report running/complete/failed like `run_hub_action` and the App Store's
//! Flatpak install job, not a live percentage — see
//! `security_container`'s module doc for why the Python progress-bar
//! parser wasn't ported.

use kyth_shared::system::jobs::{timeout_for, JobTimeoutClass};
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};

use serde::Serialize;

use kyth_shared::system::security_container::{
    self, KaliTier, DEFAULT_KALI_BOX, DEFAULT_KALI_IMAGE,
};

use super::job::{
    ensure_flathub_user_remote, failure_detail, spawn_argv_job, spawn_task_job, start_job,
    take_flatpak_slot, update_job,
};

#[derive(Serialize)]
pub(crate) struct SecurityActionLaunch {
    pub(crate) job: String,
    pub(crate) state: String,
    pub(crate) detail: String,
}

/// Single-flight for Kali box lifecycle operations (create / export /
/// remove). Create is destructive on mismatch (stop / remove / recreate)
/// and remove force-removes, so two lifecycle jobs at once — a
/// double-clicked Create, a Remove racing a Create — must not both run:
/// the second caller is rejected up front instead of racing the same box.
/// Same AtomicBool + RAII shape as the flatpak slot in `job.rs`.
static KALI_MUTATING: AtomicBool = AtomicBool::new(false);

/// RAII handle for the Kali lifecycle slot: dropping it frees the slot,
/// including on panic paths inside a job worker.
#[derive(Debug)]
pub(crate) struct KaliSlot;

impl Drop for KaliSlot {
    fn drop(&mut self) {
        KALI_MUTATING.store(false, Ordering::SeqCst);
    }
}

/// Claim the Kali lifecycle slot, or explain what must finish first.
/// Callers claim BEFORE starting their job and move the guard into the
/// job's completion closure so it is held for the job's whole life.
fn take_kali_slot() -> Result<KaliSlot, String> {
    KALI_MUTATING
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .map(|_| KaliSlot)
        .map_err(|_| {
            "Another Kali box operation (create, export, or remove) is already in progress. \
             Wait for it to finish before starting another."
                .to_string()
        })
}

/// Async + fallible: the old `-> bool` shape collapsed every probe
/// failure (podman missing, timeout, daemon down) into `false`, which
/// the UI reads as "no box" — and the natural response to "no box" is
/// Create, whose script can delete/recreate a live box. A failed probe
/// is now an `Err`, and the blocking podman call runs off the command
/// thread.
#[tauri::command]
pub(crate) async fn kali_status() -> Result<bool, String> {
    tauri::async_runtime::spawn_blocking(|| {
        security_container::probe_kali_box(DEFAULT_KALI_BOX)
            .map(|info| info.is_some_and(|info| info.socket_capable()))
    })
    .await
    .map_err(|err| format!("Kali status check failed: {err}"))?
}

#[tauri::command]
pub(crate) fn kali_create(tier: String) -> Result<SecurityActionLaunch, String> {
    let parsed = KaliTier::parse(&tier).ok_or_else(|| "unknown Kali tier".to_string())?;
    let argv = security_container::build_kali_create_command(
        DEFAULT_KALI_BOX,
        DEFAULT_KALI_IMAGE,
        parsed,
    )?;
    let slot = take_kali_slot()?;
    let job = start_job("kali-create", "Pulling Kali container image…")?;
    // kali-linux-everything can pull 15-20GB; give it real headroom.
    spawn_argv_job(
        job.clone(),
        argv,
        timeout_for(JobTimeoutClass::ExtendedWork),
        move |result| {
            let _slot = slot;
            match result {
                Ok(output) if output.status.success() => (
                    "complete".to_string(),
                    if parsed.has_gui() {
                        "Kali box created. GUI apps exported — check your application menu."
                            .to_string()
                    } else {
                        "Kali box created. Launch a terminal to start hacking.".to_string()
                    },
                ),
                Ok(output) => ("failed".to_string(), failure_detail("Kali setup", &output)),
                Err(err) => (
                    "failed".to_string(),
                    format!("Could not start Kali setup: {err}"),
                ),
            }
        },
    );
    Ok(SecurityActionLaunch {
        job,
        state: "running".into(),
        detail: "Pulling Kali container image…".into(),
    })
}

#[tauri::command]
pub(crate) fn kali_export() -> Result<SecurityActionLaunch, String> {
    let argv = security_container::build_kali_export_command(DEFAULT_KALI_BOX)?;
    let slot = take_kali_slot()?;
    let job = start_job("kali-export", "Scanning Kali container for GUI apps…")?;
    spawn_argv_job(
        job.clone(),
        argv,
        timeout_for(JobTimeoutClass::ContainerScan),
        move |result| {
            let _slot = slot;
            match result {
        Ok(output) if output.status.code() == Some(2) => (
            "complete".to_string(),
            "No GUI apps found. kali-linux-headless only includes CLI tools. Re-create the box \
             with 'Default' or 'Everything' to get exportable GUI apps."
                .to_string(),
        ),
        Ok(output) if output.status.success() => {
            let export = security_container::parse_kali_export_result(&String::from_utf8_lossy(&output.stdout));
            let Some((count, failed)) = export else {
                return ("failed".to_string(), "Kali export command finished without a valid result; inspect the container and try again.".to_string());
            };
            if count == 0 && failed > 0 {
                ("failed".to_string(), format!("Could not export any GUI apps ({failed} failed). Check distrobox-export output and retry."))
            } else if count == 0 {
                (
                    "complete".to_string(),
                    "No GUI apps exported. kali-linux-headless contains CLI tools only — remove this \
                     box and re-create it with 'Default' or 'Everything' to get exportable GUI apps."
                        .to_string(),
                )
            } else {
                let detail = if failed > 0 {
                    format!("Exported {count} app(s); {failed} failed. Check the container output for skipped apps.")
                } else {
                    format!("Exported {count} app(s) — they should appear in your application menu shortly.")
                };
                ("complete".to_string(), detail)
            }
        }
        Ok(output) => ("failed".to_string(), failure_detail("Export", &output)),
        Err(err) => ("failed".to_string(), format!("Could not start export: {err}")),
    }
        },
    );
    Ok(SecurityActionLaunch {
        job,
        state: "running".into(),
        detail: "Scanning Kali container for GUI apps…".into(),
    })
}

#[tauri::command]
pub(crate) fn kali_remove() -> Result<SecurityActionLaunch, String> {
    let argv = security_container::build_kali_remove_command(DEFAULT_KALI_BOX)?;
    let slot = take_kali_slot()?;
    let job = start_job("kali-remove", "Stopping and removing Kali box…")?;
    spawn_argv_job(
        job.clone(),
        argv,
        timeout_for(JobTimeoutClass::QuickRemove),
        move |result| {
            let _slot = slot;
            match result {
                Ok(output) if output.status.success() => {
                    ("complete".to_string(), "Kali box removed.".to_string())
                }
                Ok(output) => ("failed".to_string(), failure_detail("Removal", &output)),
                Err(err) => (
                    "failed".to_string(),
                    format!("Could not start removal: {err}"),
                ),
            }
        },
    );
    Ok(SecurityActionLaunch {
        job,
        state: "running".into(),
        detail: "Stopping and removing Kali box…".into(),
    })
}

#[tauri::command]
pub(crate) fn kali_enter_terminal() -> Result<String, String> {
    let terminal = security_container::detect_terminal()
        .ok_or_else(|| "Could not find a terminal emulator to open.".to_string())?;
    let argv = security_container::kali_enter_argv(terminal, DEFAULT_KALI_BOX);
    kyth_shared::system::process::spawn_detached(Command::new(&argv[0]).args(&argv[1..]))
        .map_err(|err| format!("could not open a terminal: {err}"))?;
    Ok("Opened a Kali terminal.".to_string())
}

#[tauri::command]
pub(crate) fn security_job_status(job: String) -> crate::InstallStatus {
    super::job::job_status(job)
}

#[tauri::command]
pub(crate) fn security_job_cancel(job: String) -> crate::InstallStatus {
    super::job::cancel_job(job)
}

#[derive(Serialize)]
pub(crate) struct SecHostToolResponse {
    flatpak: String,
    name: String,
    desc: String,
    installed: bool,
    /// Scopes whose flatpak scan failed during this read (a subset of
    /// `"user"` / `"system"`); non-empty means `installed` may be
    /// incomplete and the UI should say "couldn't check" rather than
    /// trust the flags.
    scan_failed_scopes: Vec<String>,
}

/// Async + one scan, same reasoning as `gaming_tools`.
#[tauri::command]
pub(crate) async fn sec_host_tools() -> Vec<SecHostToolResponse> {
    tauri::async_runtime::spawn_blocking(|| {
        let ids: Vec<&str> = security_container::SEC_HOST_TOOLS
            .iter()
            .map(|tool| tool.flatpak)
            .collect();
        // The scan-based read, not `installed_flatpaks()`: a failed scope
        // used to be silently dropped, reporting every tool "not
        // installed" and inviting a redundant reinstall. The failure is
        // logged and carried to the UI in `scan_failed_scopes`.
        let scan = kyth_shared::system::software_catalog::installed_flatpaks_scan();
        if !scan.failed_scopes.is_empty() {
            eprintln!(
                "sec_host_tools: flatpak scan failed for scope(s): {}",
                scan.failed_scopes.join(", ")
            );
        }
        let scan_failed_scopes = scan.failed_scopes.clone();
        let flags = kyth_shared::system::software_catalog::installed_flags(&ids, || scan.apps);
        security_container::SEC_HOST_TOOLS
            .iter()
            .zip(flags)
            .map(|(tool, installed)| SecHostToolResponse {
                flatpak: tool.flatpak.to_string(),
                name: tool.name.to_string(),
                desc: tool.desc.to_string(),
                installed,
                scan_failed_scopes: scan_failed_scopes.clone(),
            })
            .collect()
    })
    .await
    .unwrap_or_else(|err| {
        eprintln!("sec_host_tools: scan task failed: {err}");
        Vec::new()
    })
}

fn validated_sec_tool(
    flatpak_id: &str,
) -> Result<&'static security_container::SecHostTool, String> {
    security_container::find_sec_host_tool(flatpak_id)
        .ok_or_else(|| "unknown security tool".to_string())
}

#[tauri::command(rename_all = "snake_case")]
pub(crate) fn sec_host_tool_install(flatpak_id: String) -> Result<SecurityActionLaunch, String> {
    let tool = validated_sec_tool(&flatpak_id)?;
    // Shared flatpak single-flight, claimed before the job exists.
    let slot = take_flatpak_slot()?;
    let name = tool.name.to_string();
    let launch_detail = format!("Installing {name}…");
    // No shell: the flatpak id is catalog-validated, but argv form removes
    // even the theoretical injection surface that `bash -c` with an
    // interpolated id had. The Flathub remote-add runs INSIDE the tracked
    // job now: it used to run synchronously on this command thread, so a
    // stalled remote-add froze the whole Hub window for up to 60 s.
    let job = start_job("sec-install", &launch_detail)?;
    let worker_name = name.clone();
    spawn_task_job(job.clone(), move |worker_job, cancel| {
        // Held until the task returns so the slot covers the whole job.
        let _slot = slot;
        update_job(&worker_job, "Setting up Flathub…");
        if let Err(error) = ensure_flathub_user_remote(&cancel) {
            return (
                "failed".into(),
                format!("Could not set up Flathub: {error}"),
            );
        }
        if cancel.load(std::sync::atomic::Ordering::Relaxed) {
            return ("cancelled".into(), "Cancelled.".into());
        }
        update_job(&worker_job, &format!("Installing {worker_name}…"));
        let mut command = Command::new("/usr/bin/flatpak");
        command.args(["install", "--user", "-y", "flathub", "--", &flatpak_id]);
        match kyth_shared::system::process::run_bounded_command_cancel(
            command,
            timeout_for(JobTimeoutClass::FlatpakTransfer),
            &cancel,
        ) {
            Ok(output) if output.status.success() => {
                ("complete".into(), format!("{worker_name} installed."))
            }
            Ok(output) => ("failed".into(), failure_detail("Installation", &output)),
            Err(err) => {
                let detail = match err.kind() {
                    std::io::ErrorKind::TimedOut => {
                        "Installation took too long and was stopped.".to_string()
                    }
                    std::io::ErrorKind::Interrupted => "Installation was cancelled.".to_string(),
                    _ => format!("Could not start installation: {err}"),
                };
                ("failed".into(), detail)
            }
        }
    });
    Ok(SecurityActionLaunch {
        job,
        state: "running".into(),
        detail: launch_detail,
    })
}

#[tauri::command(rename_all = "snake_case")]
pub(crate) fn sec_host_tool_uninstall(flatpak_id: String) -> Result<SecurityActionLaunch, String> {
    let tool = validated_sec_tool(&flatpak_id)?;
    let slot = take_flatpak_slot()?;
    let name = tool.name.to_string();
    let launch_detail = format!("Uninstalling {name}…");
    // Pin the user scope: an unscoped uninstall can target (or prompt for)
    // the system installation instead of the per-user one this grid manages.
    let argv = vec![
        "/usr/bin/flatpak".to_string(),
        "uninstall".to_string(),
        "--user".to_string(),
        "-y".to_string(),
        flatpak_id,
    ];
    let job = start_job("sec-uninstall", &format!("Uninstalling {name}…"))?;
    spawn_argv_job(
        job.clone(),
        argv,
        timeout_for(JobTimeoutClass::QuickRemove),
        // The slot guard rides in the completion closure, which
        // spawn_argv_job owns inside the worker for the whole run.
        move |result| {
            let _slot = slot;
            match result {
                Ok(output) if output.status.success() => {
                    ("complete".to_string(), format!("{name} uninstalled."))
                }
                Ok(output) => ("failed".to_string(), failure_detail("Uninstall", &output)),
                Err(err) => (
                    "failed".to_string(),
                    format!("Could not start uninstall: {err}"),
                ),
            }
        },
    );
    Ok(SecurityActionLaunch {
        job,
        state: "running".into(),
        detail: launch_detail,
    })
}

#[tauri::command(rename_all = "snake_case")]
pub(crate) fn sec_host_tool_launch(flatpak_id: String) -> Result<String, String> {
    let tool = validated_sec_tool(&flatpak_id)?;
    // A detached `flatpak run` of a missing app fails where nobody reads
    // it, so check first instead of reporting "launched" for nothing.
    if !kyth_shared::system::software_catalog::is_flatpak_installed(tool.flatpak) {
        return Err(format!("{} is not installed.", tool.name));
    }
    kyth_shared::system::process::spawn_detached(
        Command::new("/usr/bin/flatpak").args(["run", tool.flatpak]),
    )
    .map_err(|err| format!("could not launch {}: {err}", tool.name))?;
    Ok(format!("{} launched.", tool.name))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn kali_slot_is_single_flight_until_dropped() {
        let first = take_kali_slot().expect("first claim succeeds");
        let second = take_kali_slot();
        assert!(
            second.is_err(),
            "a second Kali lifecycle op must be rejected while one runs"
        );
        assert!(second.unwrap_err().contains("already in progress"));
        drop(first);
        assert!(
            take_kali_slot().is_ok(),
            "dropping the guard frees the slot"
        );
    }
}
