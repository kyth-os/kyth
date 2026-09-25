//! Dev Tools page bridge: AI dev-box (`kyth-ai-dev` distrobox) status and
//! creation, plus the "vibe coder" setup wizard — per-tool catalog,
//! selection-driven install, and per-tool status. Catalog and command
//! builders live in `kyth_shared::system::{ai_dev, dev_tools_catalog}`.

use std::path::PathBuf;

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

#[tauri::command]
pub(crate) fn ai_dev_box_status() -> AiDevBoxStatus {
    let config = config();
    let exists = ai_dev::box_exists(&config).unwrap_or(false);
    AiDevBoxStatus {
        exists,
        box_name: config.box_name,
        gpu: ai_dev::gpu_description(ai_dev::gpu_kind()).to_string(),
    }
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
    let resolved = dev_tools_catalog::resolve_selection(selected_ids);
    if resolved.is_empty() {
        return Err("None of the selected tools are recognized.".to_string());
    }
    Ok(resolved)
}

/// Run the wizard end to end: create `kyth-ai-dev` if it does not exist yet,
/// provision every in-box tool the user picked in one script, then run each
/// host-level tool's own install command in sequence. Reported as a single
/// tracked job so the wizard's progress view has one thing to poll, with
/// `update_job` phase text marking which stage is running.
#[tauri::command]
pub(crate) fn dev_tools_install_selection(
    selected_ids: Vec<String>,
) -> Result<DevToolsActionLaunch, String> {
    let selected = validate_selection(&selected_ids)?;
    let config = config();
    let launch_detail = "Preparing the dev box…".to_string();
    let job = start_job("dev-tools-install", &launch_detail)?;

    let box_config = config.clone();
    let selected_owned: Vec<&'static dev_tools_catalog::DevTool> = selected;
    spawn_task_job(job.clone(), move |worker_job, cancel| {
        use super::job::update_job;
        use std::sync::atomic::Ordering::Relaxed;

        if !ai_dev::box_exists(&box_config).unwrap_or(false) {
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
                &cancel,
            ) {
                Ok(output) if output.status.success() => {}
                Ok(output) => {
                    return ("failed".into(), failure_detail("Dev box creation", &output))
                }
                Err(error) => {
                    return (
                        "failed".into(),
                        format!("Could not create the dev box: {error}"),
                    )
                }
            }
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
                &cancel,
            ) {
                Ok(output) if output.status.success() => {}
                Ok(output) => return ("failed".into(), failure_detail("Tool install", &output)),
                Err(error) => {
                    return (
                        "failed".into(),
                        format!("Could not install the selected tools: {error}"),
                    )
                }
            }
        }
        if cancel.load(Relaxed) {
            return ("cancelled".into(), "Cancelled.".into());
        }

        for tool in selected_owned.iter().filter(|tool| {
            matches!(
                tool.install,
                InstallMethod::HostScript(_) | InstallMethod::HostRpmUrl(_)
            )
        }) {
            update_job(&worker_job, &format!("Installing {}…", tool.name));
            let Some(argv) = ai_dev::host_install_command(tool) else {
                continue;
            };
            let (program, args) = match argv.split_first() {
                Some(parts) => parts,
                None => continue,
            };
            let mut command = std::process::Command::new(program);
            command.args(args);
            match kyth_shared::system::process::run_bounded_command_cancel(
                command,
                timeout_for(JobTimeoutClass::ToolInstall),
                &cancel,
            ) {
                Ok(output) if output.status.success() => {}
                Ok(output) => {
                    return (
                        "failed".into(),
                        failure_detail(&format!("{} install", tool.name), &output),
                    )
                }
                Err(error) => {
                    return (
                        "failed".into(),
                        format!("Could not install {}: {error}", tool.name),
                    )
                }
            }
            if cancel.load(Relaxed) {
                return ("cancelled".into(), "Cancelled.".into());
            }
        }

        (
            "complete".into(),
            format!("Installed {} tool(s).", selected_owned.len()),
        )
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
        assert!(validate_selection(&["vscode".to_string()]).is_ok());
    }

    #[test]
    fn catalog_list_reports_every_tool_with_a_category_label() {
        let list = dev_tools_catalog_list();
        assert_eq!(list.len(), DEV_TOOLS.len());
        assert!(list.iter().all(|tool| !tool.category_label.is_empty()));
    }
}
