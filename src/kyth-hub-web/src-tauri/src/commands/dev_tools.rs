//! Dev Tools page bridge: AI dev-box (`kyth-ai-dev` distrobox) status and
//! creation, plus the "vibe coder" setup wizard — per-tool catalog,
//! selection-driven install, and per-tool status. Catalog and command
//! builders live in `kyth_shared::system::{ai_dev, dev_tools_catalog}`.

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use serde::Serialize;

use kyth_shared::system::ai_dev::{self, Config};
use kyth_shared::system::dev_tools_catalog::{self, InstallMethod, DEV_TOOLS};
use kyth_shared::system::jobs::{timeout_for, JobTimeoutClass};

use super::job::{failure_detail, spawn_task_job, start_job};

fn config() -> Config {
    let environment = std::env::vars().collect();
    Config::from_environment(&environment)
}

fn home_dir() -> PathBuf {
    std::env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
}

// ---------------------------------------------------------------------
// Catalog + status
// ---------------------------------------------------------------------

#[derive(Serialize)]
pub(crate) struct DevToolResponse {
    id: String,
    name: String,
    category: String,
    category_label: String,
    description: String,
    unofficial: bool,
    default_selected: bool,
    installed: bool,
}

#[tauri::command]
pub(crate) fn dev_tools_catalog_list() -> Vec<DevToolResponse> {
    DEV_TOOLS
        .iter()
        .map(|tool| DevToolResponse {
            id: tool.id.to_string(),
            name: tool.name.to_string(),
            category: tool.category.key().to_string(),
            category_label: tool.category.label().to_string(),
            description: tool.description.to_string(),
            unofficial: tool.unofficial,
            default_selected: tool.default_selected,
            installed: ai_dev::dev_tool_is_installed(tool),
        })
        .collect()
}

#[derive(Serialize)]
pub(crate) struct AiDevBoxStatus {
    exists: bool,
    box_name: String,
    gpu: String,
}

/// Fallible: the old shape swallowed every probe error into
/// `exists: false`, which the wizard reads as "no box" — and creation
/// is existence-gated, so a failed probe invited a recreate of a live
/// box. Runs on the blocking pool: `distrobox list` alone is bounded
/// at 120 s, far too long to stall the command thread.
#[tauri::command]
pub(crate) async fn ai_dev_box_status() -> Result<AiDevBoxStatus, String> {
    tauri::async_runtime::spawn_blocking(|| {
        let config = config();
        let exists = ai_dev::box_exists(&config)
            .map_err(|error| format!("Could not check whether the dev box exists: {error}"))?;
        Ok(AiDevBoxStatus {
            exists,
            box_name: config.box_name,
            gpu: ai_dev::gpu_description(ai_dev::gpu_kind()).to_string(),
        })
    })
    .await
    .map_err(|err| format!("Dev box status check failed: {err}"))?
}

// ---------------------------------------------------------------------
// Wizard: create the box (if missing) + install exactly the selection
// ---------------------------------------------------------------------

#[derive(Serialize)]
pub(crate) struct DevToolsActionLaunch {
    pub(crate) job: String,
    pub(crate) state: String,
    pub(crate) detail: String,
}

fn validate_selection(
    selected_ids: &[String],
) -> Result<Vec<&'static dev_tools_catalog::DevTool>, String> {
    if selected_ids.is_empty() {
        return Err("Pick at least one tool to install.".to_string());
    }
    if selected_ids.len() > 64 {
        // Generous ceiling: the whole catalog today is under 20 entries.
        // Guards a malformed/replayed request rather than a real user pick.
        return Err("Too many tools selected.".to_string());
    }
    // resolve_selection preserves repeats, so without this check one
    // request could run the same host installer twice (and provision
    // the same in-box tool twice) for a duplicated id.
    let mut seen = std::collections::HashSet::new();
    if selected_ids.iter().any(|id| !seen.insert(id.as_str())) {
        return Err(
            "The selection lists the same tool more than once. Refresh the catalog and try again."
                .to_string(),
        );
    }
    let resolved = dev_tools_catalog::resolve_selection(selected_ids);
    if resolved.is_empty() {
        return Err("None of the selected tools are recognized.".to_string());
    }
    if resolved.len() != selected_ids.len() {
        return Err("One or more selected tools are no longer available. Refresh the catalog and try again.".to_string());
    }
    if let Some(tool) = resolved
        .iter()
        .find(|tool| matches!(tool.install, InstallMethod::Manual(_)))
    {
        let InstallMethod::Manual(url) = tool.install else {
            unreachable!();
        };
        return Err(format!("{} needs manual installation: {url}", tool.name));
    }
    Ok(resolved)
}

/// Single-flight for the dev-tools wizard install. Two runs at once
/// would create/provision the same `kyth-ai-dev` box concurrently and
/// run the same host installer scripts (incl. `sudo dnf`) in parallel.
/// Same AtomicBool + RAII shape as the flatpak slot in `job.rs`.
static DEV_TOOLS_INSTALLING: AtomicBool = AtomicBool::new(false);

/// RAII handle for the wizard slot: dropping it frees the slot,
/// including on panic paths inside the job worker.
#[derive(Debug)]
struct DevToolsSlot;

impl Drop for DevToolsSlot {
    fn drop(&mut self) {
        DEV_TOOLS_INSTALLING.store(false, Ordering::SeqCst);
    }
}

/// Claim the wizard slot, or explain what must finish first. Callers
/// claim BEFORE starting their job and move the guard into the task so
/// it is held for the job's whole life.
fn take_dev_tools_slot() -> Result<DevToolsSlot, String> {
    DEV_TOOLS_INSTALLING
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .map(|_| DevToolsSlot)
        .map_err(|_| {
            "Another dev tools install is already in progress. \
             Wait for it to finish before starting another."
                .to_string()
        })
}

/// Overall deadline for one wizard run: the chain's own worst case —
/// box creation and in-box provisioning are each an `ExtendedWork`
/// step, and every host-level tool is a `ToolInstall` step.
/// `spawn_task_job` has no job-level timeout, so the task enforces this
/// budget itself (see the watchdog in `dev_tools_install_selection`).
fn install_budget(host_tool_count: usize) -> Duration {
    let host_steps = u32::try_from(host_tool_count).unwrap_or(u32::MAX);
    timeout_for(JobTimeoutClass::ExtendedWork) * 2
        + timeout_for(JobTimeoutClass::ToolInstall) * host_steps
}

/// Split the selection's host-level tools into ones whose installer
/// still needs to run and ones already present on the host. A host
/// installer is a downloaded script or a `sudo dnf` transaction —
/// re-running one for an already-installed tool wastes the wait and
/// can churn a working install, so the wizard skips those and says so.
/// The probe is injected so tests can stub it; production passes
/// `ai_dev::dev_tool_is_installed`, the same probe the catalog list
/// renders `installed` from, so the wizard and the list cannot
/// disagree about what is already there.
fn host_tools_needing_install<'a>(
    selected: &[&'a dev_tools_catalog::DevTool],
    is_installed: impl Fn(&dev_tools_catalog::DevTool) -> bool,
) -> (
    Vec<&'a dev_tools_catalog::DevTool>,
    Vec<&'a dev_tools_catalog::DevTool>,
) {
    let mut to_install = Vec::new();
    let mut already_installed = Vec::new();
    for tool in selected.iter().copied().filter(|tool| {
        matches!(
            tool.install,
            InstallMethod::HostScript { .. } | InstallMethod::HostRpmUrl(_)
        )
    }) {
        if is_installed(tool) {
            already_installed.push(tool);
        } else {
            to_install.push(tool);
        }
    }
    (to_install, already_installed)
}

/// Sets the flag on drop; stops the install watchdog on every task exit.
struct WatchdogStop(Arc<AtomicBool>);

impl Drop for WatchdogStop {
    fn drop(&mut self) {
        self.0.store(true, Ordering::Relaxed);
    }
}

/// Run the wizard end to end: create `kyth-ai-dev` if it does not exist yet,
/// provision every in-box tool the user picked in one script, then run each
/// host-level tool's own install command in sequence. Reported as a single
/// tracked job so the wizard's progress view has one thing to poll, with
/// `update_job` phase text marking which stage is running.
#[tauri::command(rename_all = "snake_case")]
pub(crate) fn dev_tools_install_selection(
    selected_ids: Vec<String>,
) -> Result<DevToolsActionLaunch, String> {
    let selected = validate_selection(&selected_ids)?;
    // Wizard single-flight, claimed before the job exists.
    let slot = take_dev_tools_slot()?;
    let config = config();
    let launch_detail = "Preparing the dev box…".to_string();
    let job = start_job("dev-tools-install", &launch_detail)?;

    let box_config = config.clone();
    let selected_owned: Vec<&'static dev_tools_catalog::DevTool> = selected;
    let host_tool_count = selected_owned
        .iter()
        .filter(|tool| {
            matches!(
                tool.install,
                InstallMethod::HostScript { .. } | InstallMethod::HostRpmUrl(_)
            )
        })
        .count();
    let budget = install_budget(host_tool_count);
    spawn_task_job(job.clone(), move |worker_job, cancel| {
        use super::job::update_job;
        use std::sync::atomic::Ordering::Relaxed;

        // Held until the task returns so the slot covers the whole job.
        let _slot = slot;

        // Job-level deadline. `spawn_task_job` imposes none, and the
        // chain's per-step timeouts sum to `budget` in the worst case —
        // and a step wedged outside a bounded command would never end
        // at all. A watchdog folds the deadline (and the job's own
        // cancel flag) into a local flag handed to the bounded runner,
        // so an in-flight step is killed at the deadline instead of
        // whenever it happens to finish.
        let deadline = Instant::now() + budget;
        let effective_cancel = Arc::new(AtomicBool::new(false));
        let watchdog_stop = Arc::new(AtomicBool::new(false));
        {
            let job_cancel = cancel.clone();
            let effective = effective_cancel.clone();
            let stop = watchdog_stop.clone();
            std::thread::spawn(move || {
                while !stop.load(Relaxed) {
                    if job_cancel.load(Relaxed) || Instant::now() >= deadline {
                        effective.store(true, Relaxed);
                        break;
                    }
                    std::thread::sleep(Duration::from_millis(100));
                }
            });
        }
        let _watchdog_stop = WatchdogStop(watchdog_stop);
        let past_deadline = || Instant::now() >= deadline;

        let box_exists = match ai_dev::box_exists(&box_config) {
            Ok(exists) => exists,
            Err(error) => {
                return (
                    "failed".into(),
                    format!("Could not check whether the dev box exists: {error}"),
                )
            }
        };
        if !box_exists {
            update_job(&worker_job, "Creating the dev box…");
            let home = home_dir();
            let gpu = ai_dev::gpu_kind();
            let create_argv = ai_dev::create_command_for_host(&box_config, &home, gpu);
            let (program, args) = match create_argv.split_first() {
                Some(parts) => parts,
                None => {
                    return (
                        "failed".into(),
                        "Could not build the create command.".into(),
                    )
                }
            };
            let mut command = std::process::Command::new(program);
            command.args(args);
            match kyth_shared::system::process::run_bounded_command_cancel(
                command,
                timeout_for(JobTimeoutClass::ExtendedWork),
                &effective_cancel,
            ) {
                Ok(output) if output.status.success() => {}
                Ok(output) => {
                    return ("failed".into(), failure_detail("Dev box creation", &output))
                }
                Err(error) => {
                    if past_deadline() {
                        return (
                            "failed".into(),
                            "Dev tools setup took too long and was stopped.".into(),
                        );
                    }
                    if cancel.load(Relaxed) {
                        return ("cancelled".into(), "Cancelled.".into());
                    }
                    return (
                        "failed".into(),
                        format!("Could not create the dev box: {error}"),
                    );
                }
            }
        }
        if past_deadline() {
            return (
                "failed".into(),
                "Dev tools setup took too long and was stopped.".into(),
            );
        }
        if cancel.load(Relaxed) {
            return ("cancelled".into(), "Cancelled.".into());
        }

        if let Some(argv) = ai_dev::provision_command_for_selection(&box_config, &selected_owned) {
            update_job(&worker_job, "Installing selected tools in the dev box…");
            let (program, args) = match argv.split_first() {
                Some(parts) => parts,
                None => {
                    return (
                        "failed".into(),
                        "Could not build the install command.".into(),
                    )
                }
            };
            let mut command = std::process::Command::new(program);
            command.args(args);
            match kyth_shared::system::process::run_bounded_command_cancel(
                command,
                timeout_for(JobTimeoutClass::ExtendedWork),
                &effective_cancel,
            ) {
                Ok(output) if output.status.success() => {}
                Ok(output) => return ("failed".into(), failure_detail("Tool install", &output)),
                Err(error) => {
                    if past_deadline() {
                        return (
                            "failed".into(),
                            "Dev tools setup took too long and was stopped.".into(),
                        );
                    }
                    if cancel.load(Relaxed) {
                        return ("cancelled".into(), "Cancelled.".into());
                    }
                    return (
                        "failed".into(),
                        format!("Could not install the selected tools: {error}"),
                    );
                }
            }
        }
        if past_deadline() {
            return (
                "failed".into(),
                "Dev tools setup took too long and was stopped.".into(),
            );
        }
        if cancel.load(Relaxed) {
            return ("cancelled".into(), "Cancelled.".into());
        }

        let (host_to_install, host_skipped) =
            host_tools_needing_install(&selected_owned, ai_dev::dev_tool_is_installed);
        for tool in &host_skipped {
            update_job(
                &worker_job,
                &format!("{} is already installed; skipping.", tool.name),
            );
        }
        let skipped_names: Vec<&str> = host_skipped.iter().map(|tool| tool.name).collect();
        for tool in host_to_install.iter() {
            update_job(&worker_job, &format!("Installing {}…", tool.name));
            let Some(argv) = ai_dev::host_install_command(tool) else {
                return (
                    "failed".into(),
                    format!("Could not build the {} install command.", tool.name),
                );
            };
            let (program, args) = match argv.split_first() {
                Some(parts) => parts,
                None => {
                    return (
                        "failed".into(),
                        format!("Could not build the {} install command.", tool.name),
                    )
                }
            };
            let mut command = std::process::Command::new(program);
            command.args(args);
            match kyth_shared::system::process::run_bounded_command_cancel(
                command,
                timeout_for(JobTimeoutClass::ToolInstall),
                &effective_cancel,
            ) {
                Ok(output) if output.status.success() => {}
                Ok(output) => {
                    return (
                        "failed".into(),
                        failure_detail(&format!("{} install", tool.name), &output),
                    )
                }
                Err(error) => {
                    if past_deadline() {
                        return (
                            "failed".into(),
                            "Dev tools setup took too long and was stopped.".into(),
                        );
                    }
                    if cancel.load(Relaxed) {
                        return ("cancelled".into(), "Cancelled.".into());
                    }
                    return (
                        "failed".into(),
                        format!("Could not install {}: {error}", tool.name),
                    );
                }
            }
            if past_deadline() {
                return (
                    "failed".into(),
                    "Dev tools setup took too long and was stopped.".into(),
                );
            }
            if cancel.load(Relaxed) {
                return ("cancelled".into(), "Cancelled.".into());
            }
        }

        if skipped_names.is_empty() {
            (
                "complete".into(),
                format!("Installed {} tool(s).", selected_owned.len()),
            )
        } else {
            (
                "complete".into(),
                format!(
                    "Installed {} tool(s). Already installed, skipped: {}.",
                    selected_owned.len() - skipped_names.len(),
                    skipped_names.join(", ")
                ),
            )
        }
    });

    Ok(DevToolsActionLaunch {
        job,
        state: "running".into(),
        detail: launch_detail,
    })
}

#[tauri::command]
pub(crate) fn dev_tools_job_status(job: String) -> crate::InstallStatus {
    super::job::job_status(job)
}

#[tauri::command]
pub(crate) fn dev_tools_job_cancel(job: String) -> crate::InstallStatus {
    super::job::cancel_job(job)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_empty_and_unknown_selection() {
        assert!(validate_selection(&[]).is_err());
        assert!(validate_selection(&["not-a-real-tool".to_string()]).is_err());
        assert!(
            validate_selection(&["vscode".to_string(), "not-a-real-tool".to_string()]).is_err()
        );
        assert!(validate_selection(&["vscode".to_string()]).is_ok());
    }

    #[test]
    fn install_budget_covers_the_chain_worst_case() {
        let base = timeout_for(JobTimeoutClass::ExtendedWork) * 2;
        let step = timeout_for(JobTimeoutClass::ToolInstall);
        assert_eq!(install_budget(0), base);
        assert_eq!(install_budget(3), base + step * 3);
        assert!(install_budget(1) > install_budget(0));
    }

    #[test]
    fn dev_tools_slot_is_single_flight_until_dropped() {
        let first = take_dev_tools_slot().expect("first claim succeeds");
        let second = take_dev_tools_slot();
        assert!(
            second.is_err(),
            "a second wizard run must be rejected while one runs"
        );
        assert!(second.unwrap_err().contains("already in progress"));
        drop(first);
        assert!(
            take_dev_tools_slot().is_ok(),
            "dropping the guard frees the slot"
        );
    }

    #[test]
    fn manual_tools_are_not_reported_as_installed_by_the_automated_wizard() {
        let error = validate_selection(&["claude-desktop".to_string()]).unwrap_err();
        assert!(error.contains("manual installation"));
        assert!(error.contains("https://"));
    }

    #[test]
    fn catalog_list_reports_every_tool_with_a_category_label() {
        let list = dev_tools_catalog_list();
        assert_eq!(list.len(), DEV_TOOLS.len());
        assert!(list.iter().all(|tool| !tool.category_label.is_empty()));
    }

    #[test]
    fn duplicate_selection_is_rejected() {
        let error = validate_selection(&["vscode".to_string(), "vscode".to_string()]).unwrap_err();
        assert!(error.contains("more than once"), "got: {error}");
        assert!(validate_selection(&[
            "vscode".to_string(),
            "git".to_string(),
            "vscode".to_string(),
        ])
        .is_err());
        // A duplicate-free selection still validates.
        assert!(validate_selection(&["vscode".to_string(), "git".to_string()]).is_ok());
    }

    #[test]
    fn host_tools_needing_install_skips_installed_and_ignores_box_tools() {
        // vscode installs inside the box; hermes-desktop is a host
        // script and codex-desktop a host RPM.
        let vscode = dev_tools_catalog::find_dev_tool("vscode").unwrap();
        let hermes = dev_tools_catalog::find_dev_tool("hermes-desktop").unwrap();
        let codex_desktop = dev_tools_catalog::find_dev_tool("codex-desktop").unwrap();
        let selected = vec![vscode, hermes, codex_desktop];

        let (to_install, skipped) =
            host_tools_needing_install(&selected, |tool| tool.id == "hermes-desktop");
        assert_eq!(to_install.len(), 1);
        assert_eq!(to_install[0].id, "codex-desktop");
        assert_eq!(skipped.len(), 1);
        assert_eq!(skipped[0].id, "hermes-desktop");

        // Nothing installed: every host tool is queued, none skipped,
        // and the in-box tool appears in neither list.
        let (to_install, skipped) = host_tools_needing_install(&selected, |_| false);
        assert_eq!(to_install.len(), 2);
        assert!(skipped.is_empty());
    }
}
