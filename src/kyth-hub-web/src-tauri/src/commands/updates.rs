use std::process::Command;
use std::sync::OnceLock;
use std::time::Duration;

use serde::{Deserialize, Serialize};

use kyth_shared::system::jobs::{timeout_for, JobStore, JobTimeoutClass};

static HUB_ACTION_JOBS: OnceLock<JobStore> = OnceLock::new();
static UPDATE_JOBS: OnceLock<JobStore> = OnceLock::new();

fn hub_action_jobs() -> &'static JobStore {
    HUB_ACTION_JOBS.get_or_init(JobStore::default)
}

fn update_jobs() -> &'static JobStore {
    UPDATE_JOBS.get_or_init(JobStore::default)
}

/// In-process slot for mutating update launches (stage/rollback/switch/
/// apply). The flock admission probe below is check-then-act: two rapid
/// invocations (double-click, two tabs) both pass it, then spawn two
/// `sudo -A` jobs that stack prompts and race on finalize. The slot closes
/// that window — the second launch fails fast with the same busy wording.
/// Cross-process serialization still rests on the flock, which each helper
/// holds for its whole run.
static UPDATE_MUTATING: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

struct MutatingSlot;

impl Drop for MutatingSlot {
    fn drop(&mut self) {
        UPDATE_MUTATING.store(false, std::sync::atomic::Ordering::SeqCst);
    }
}

fn take_mutating_slot() -> Result<MutatingSlot, String> {
    UPDATE_MUTATING
        .compare_exchange(
            false,
            true,
            std::sync::atomic::Ordering::SeqCst,
            std::sync::atomic::Ordering::SeqCst,
        )
        .map(|_| MutatingSlot)
        .map_err(|_| "Another bootc upgrade is in progress; will retry on the next run".to_string())
}

/// Latest live staging progress, streamed from `kyth-safe-upgrade` marker
/// lines while the stage job runs. The Updates page polls `stage_progress`
/// for a determinate bar; `active` is false when no stage is running.
#[derive(Serialize, Clone)]
pub(crate) struct StageProgressSnapshot {
    pub(crate) pct: u8,
    pub(crate) phase: String,
    pub(crate) detail: String,
    pub(crate) active: bool,
}

static STAGE_PROGRESS: OnceLock<std::sync::Mutex<StageProgressSnapshot>> = OnceLock::new();

fn stage_progress_cell() -> &'static std::sync::Mutex<StageProgressSnapshot> {
    STAGE_PROGRESS.get_or_init(|| {
        std::sync::Mutex::new(StageProgressSnapshot {
            pct: 0,
            phase: "download".into(),
            detail: "Starting the download…".into(),
            active: false,
        })
    })
}

/// Parse a `KYTH_STAGE_PROGRESS pct=N phase=P detail=…` marker line.
fn parse_stage_marker(line: &str) -> Option<StageProgressSnapshot> {
    let rest = line.strip_prefix("KYTH_STAGE_PROGRESS ")?;
    let pct = rest
        .split_whitespace()
        .find_map(|token| token.strip_prefix("pct=")?.parse::<u8>().ok())?;
    let phase = rest
        .split_whitespace()
        .find_map(|token| token.strip_prefix("phase="))
        .unwrap_or("download")
        .to_string();
    let detail = rest
        .find("detail=")
        .map(|idx| rest[idx + "detail=".len()..].trim().to_string())
        .filter(|text| !text.is_empty())
        .unwrap_or_else(|| {
            if phase == "install" {
                "Installing the staged image…".to_string()
            } else {
                "Downloading the update…".to_string()
            }
        });
    Some(StageProgressSnapshot {
        pct: pct.min(99),
        phase,
        detail,
        active: true,
    })
}

/// Merge a streamed marker into the current snapshot. Pure so the
/// monotonic clamp is unit-testable: a retried marker must never drag the
/// bar backwards.
fn merge_stage_snapshot(
    current: &StageProgressSnapshot,
    next: StageProgressSnapshot,
) -> StageProgressSnapshot {
    if next.pct >= current.pct {
        next
    } else {
        current.clone()
    }
}

/// Read one process-output line without letting an unterminated line allocate
/// without bound. Oversized lines are drained, capped, and never interpreted
/// as progress markers.
fn read_stage_line(
    reader: &mut impl std::io::BufRead,
    line: &mut Vec<u8>,
    limit: usize,
) -> std::io::Result<Option<bool>> {
    line.clear();
    let mut truncated = false;
    loop {
        let available = reader.fill_buf()?;
        if available.is_empty() {
            return Ok(if line.is_empty() && !truncated {
                None
            } else {
                Some(truncated)
            });
        }
        let consumed = available
            .iter()
            .position(|byte| *byte == b'\n')
            .map_or(available.len(), |index| index + 1);
        let remaining = limit.saturating_sub(line.len());
        let copied = consumed.min(remaining);
        line.extend_from_slice(&available[..copied]);
        truncated |= copied < consumed;
        let ended = available[consumed - 1] == b'\n';
        reader.consume(consumed);
        if ended {
            return Ok(Some(truncated));
        }
    }
}

/// Capture only a bounded prefix while continuing to drain the child pipe.
/// Closing a pipe at the capture limit can make a verbose helper fail with
/// EPIPE before it reaches its real result.
fn collect_bounded_output(
    reader: &mut impl std::io::Read,
    limit: usize,
) -> std::io::Result<Vec<u8>> {
    let mut collected = Vec::with_capacity(limit);
    let mut buffer = [0u8; 8192];
    let mut truncated = false;
    loop {
        let count = reader.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        let room = limit.saturating_sub(collected.len());
        let copied = count.min(room);
        collected.extend_from_slice(&buffer[..copied]);
        truncated |= copied < count;
    }
    if truncated {
        collected.extend_from_slice(b"\n...[truncated]");
    }
    Ok(collected)
}

#[tauri::command]
pub(crate) fn stage_progress() -> StageProgressSnapshot {
    stage_progress_cell()
        .lock()
        .map(|snapshot| snapshot.clone())
        .unwrap_or(StageProgressSnapshot {
            pct: 0,
            phase: "download".into(),
            detail: "Starting the download…".into(),
            active: false,
        })
}

/// Stage variant of `start_update_job` that streams the helper's stdout so
/// progress markers update the Updates page live. Cancel, timeout, and
/// terminal detail behave exactly like the non-streaming path.
fn start_stage_job(
    job_slug: &str,
    operation: &str,
    argv: Vec<String>,
    timeout: Duration,
    slot: MutatingSlot,
) -> Result<UpdateActionLaunch, String> {
    kyth_shared::commands::normalize_command(&argv)
        .map_err(|_| "update produced an invalid command".to_string())?;
    let job = format!(
        "update-{}-{}",
        job_slug,
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    let (job, cancel) = update_jobs().start(&job, format!("{operation} is running…"));
    if let Ok(mut snapshot) = stage_progress_cell().lock() {
        *snapshot = StageProgressSnapshot {
            pct: 0,
            phase: "download".into(),
            detail: "Starting the download…".into(),
            active: true,
        };
    }
    let job_for_thread = job.clone();
    let operation_for_thread = operation.to_string();
    std::thread::spawn(move || {
        // Held to the end of the job: the second mutating launch fails at
        // take_mutating_slot instead of racing this one.
        let _slot = slot;
        use std::os::unix::process::CommandExt;
        let mut command = Command::new(&argv[0]);
        command.args(&argv[1..]);
        let inherited = std::env::vars().collect::<std::collections::BTreeMap<_, _>>();
        let desktop = kyth_shared::commands::environment_for(
            kyth_shared::commands::EnvironmentPolicy::Desktop,
            &inherited,
        );
        command.env_clear().envs(desktop);
        if std::path::Path::new("/usr/bin/ksshaskpass").exists() {
            command.env("SUDO_ASKPASS", "/usr/bin/ksshaskpass");
        }
        command.process_group(0);
        command.stdin(std::process::Stdio::null());
        command.stdout(std::process::Stdio::piped());
        command.stderr(std::process::Stdio::piped());
        let spawned = command.spawn();
        let (state, detail) = match spawned {
            Ok(mut child) => {
                // Both pipes drain on helper threads from the start: a
                // chatty helper (>64 KiB on either pipe) must never wedge
                // the child, and cancel/timeout must preempt mid-download
                // instead of waiting for EOF. Captures are capped at 1 MiB
                // each (overflow is truncated and marked). A bounded line
                // reader also prevents a newline-free child write from
                // forcing `read_line` to allocate the entire pipe payload.
                const MAX_STAGE_CAPTURE_BYTES: usize = 1024 * 1024;
                const MAX_STAGE_LINE_BYTES: usize = 64 * 1024;
                let stderr_handle = child.stderr.take().map(|stderr| {
                    std::thread::spawn(move || {
                        let mut reader = std::io::BufReader::new(stderr);
                        collect_bounded_output(&mut reader, MAX_STAGE_CAPTURE_BYTES)
                            .unwrap_or_default()
                    })
                });
                let stdout_handle = child.stdout.take().map(|stdout| {
                    std::thread::spawn(move || {
                        let mut collected_out = Vec::new();
                        let mut reader = std::io::BufReader::new(stdout);
                        let mut line = Vec::new();
                        let mut truncated = false;
                        loop {
                            let line_truncated =
                                match read_stage_line(&mut reader, &mut line, MAX_STAGE_LINE_BYTES)
                                {
                                    Ok(Some(truncated)) => truncated,
                                    Ok(None) | Err(_) => break,
                                };
                            let line_text = String::from_utf8_lossy(&line);
                            if !line_truncated {
                                if let Some(snapshot) = parse_stage_marker(line_text.trim()) {
                                    if let Ok(mut cell) = stage_progress_cell().lock() {
                                        let merged = merge_stage_snapshot(&cell, snapshot);
                                        *cell = merged;
                                    }
                                    continue;
                                }
                            }
                            if collected_out.len() < MAX_STAGE_CAPTURE_BYTES {
                                let room = MAX_STAGE_CAPTURE_BYTES - collected_out.len();
                                collected_out.extend_from_slice(&line[..line.len().min(room)]);
                            } else if !truncated {
                                collected_out.extend_from_slice(b"\n...[truncated]");
                                truncated = true;
                            }
                        }
                        collected_out
                    })
                });
                // Mirror run_bounded_command_cancel: poll for exit, kill the
                // whole process group on cancel or timeout.
                let started = std::time::Instant::now();
                let outcome = loop {
                    match child.try_wait() {
                        Ok(Some(status)) => break Ok(status),
                        Ok(None) => {}
                        Err(error) => break Err(error),
                    }
                    if cancel.load(std::sync::atomic::Ordering::Relaxed) {
                        kyth_shared::system::process::kill_process_group(&mut child);
                        break Err(std::io::Error::new(
                            std::io::ErrorKind::Interrupted,
                            "command was cancelled",
                        ));
                    }
                    if started.elapsed() > timeout {
                        kyth_shared::system::process::kill_process_group(&mut child);
                        break Err(std::io::Error::new(
                            std::io::ErrorKind::TimedOut,
                            "command timed out",
                        ));
                    }
                    std::thread::sleep(Duration::from_millis(25));
                };
                // Pipes close on exit/kill, so both readers terminate; join
                // them for the terminal detail.
                let collected_out = stdout_handle
                    .and_then(|handle| handle.join().ok())
                    .unwrap_or_default();
                let collected_err = stderr_handle
                    .and_then(|handle| handle.join().ok())
                    .unwrap_or_default();
                match outcome {
                    Ok(status) => {
                        let mut detail = String::from_utf8_lossy(&collected_out).trim().to_string();
                        let stderr = String::from_utf8_lossy(&collected_err).trim().to_string();
                        if !stderr.is_empty() {
                            if !detail.is_empty() {
                                detail.push('\n');
                            }
                            detail.push_str(&stderr);
                        }
                        let detail: String = kyth_shared::system::process::redact_sensitive_text(
                            kyth_shared::system::process::strip_ansi(&detail).as_str(),
                        )
                        .chars()
                        .rev()
                        .take(1200)
                        .collect::<String>()
                        .chars()
                        .rev()
                        .collect();
                        let state = if status.success() {
                            "complete"
                        } else {
                            "failed"
                        };
                        let detail = if detail.is_empty() {
                            if status.success() {
                                format!("{operation_for_thread} complete.")
                            } else {
                                format!(
                                    "{operation_for_thread} failed (exit code {}).",
                                    status.code().unwrap_or(-1)
                                )
                            }
                        } else {
                            detail
                        };
                        (state.to_string(), detail)
                    }
                    Err(error) => (
                        "failed".to_string(),
                        format!("{operation_for_thread} could not complete: {error}"),
                    ),
                }
            }
            Err(error) => (
                "failed".to_string(),
                format!("{operation_for_thread} could not start: {error}"),
            ),
        };
        if let Ok(mut snapshot) = stage_progress_cell().lock() {
            snapshot.active = false;
        }
        update_jobs().finish(&job_for_thread, &state, detail);
    });
    Ok(UpdateActionLaunch {
        job,
        state: "running".into(),
        detail: format!("{operation} is running…"),
    })
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
        .map(|recipe| JustRecipeResponse {
            name: recipe.name,
            params: recipe.params,
            comment: recipe.comment,
        })
        .collect()
}

fn just_output_detail(recipe: &str, output: &std::process::Output) -> String {
    let mut text = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr);
    if !stderr.trim().is_empty() {
        if !text.is_empty() {
            text.push('\n');
        }
        text.push_str(&stderr);
    }
    let text = kyth_shared::system::process::redact_sensitive_text(
        kyth_shared::system::process::strip_ansi(text.trim()).as_str(),
    );
    let detail: String = text
        .chars()
        .rev()
        .take(800)
        .collect::<String>()
        .chars()
        .rev()
        .collect();
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

#[derive(Serialize)]
pub(crate) struct HubActionLaunch {
    pub(crate) job: String,
    pub(crate) state: String,
    pub(crate) detail: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub(crate) enum HubAction {
    SetupTailscale,
    UpdateHealth,
    ResumeCheck,
    DeviceInfo,
    StartupApps,
    FirmwareUpdate,
    HealthCheck,
    GamingStackStatus,
    FixDualbootClock,
    SetupBootWindowsSteam,
    ReclaimWindows,
    InstallLudusavi,
    InstallMsFonts,
    SetupKythDevBox,
    AiDevStatus,
    AiDevSetup,
    SetupWaydroid,
    RemoveWaydroid,
    InstallVscode,
    InstallBoxbuddy,
    InstallJetbrainsToolbox,
    GamingMode,
    BalancedMode,
    HdrPerGame,
    EnableBpftune,
    DisableBpftune,
    InstallSteam,
    InstallHeroic,
    InstallLutris,
    InstallBottles,
    InstallPrismlauncher,
    InstallItch,
    InstallEpicLauncher,
    InstallBattlenet,
    InstallEaApp,
    InstallUbisoftConnect,
    PreheatShaders,
    EnableObsCapture,
    GameBoost,
    ControllerCheck,
    ExportSteamGames,
    InstallObs,
    InstallGpuScreenRecorder,
    InstallGoverlay,
    InstallMangojuice,
    InstallUmu,
    InstallLact,
    InstallPiper,
    InstallSolaar,
    NvidiaStatus,
    ListPresets,
    SetupPrinter,
    EnrollSecureboot,
    SystemAudit,
    GamingAudit,
}

impl HubAction {
    fn recipe(&self) -> &'static str {
        match self {
            Self::SetupTailscale => "setup-tailscale",
            Self::UpdateHealth => "update-health",
            Self::ResumeCheck => "resume-check",
            Self::DeviceInfo => "device-info",
            Self::StartupApps => "startup-apps",
            Self::FirmwareUpdate => "firmware-update",
            Self::HealthCheck => "health-check",
            Self::GamingStackStatus => "gaming-stack-status",
            Self::FixDualbootClock => "fix-dualboot-clock",
            Self::SetupBootWindowsSteam => "setup-boot-windows-steam",
            Self::ReclaimWindows => "reclaim-windows",
            Self::InstallLudusavi => "install-ludusavi",
            Self::InstallMsFonts => "install-ms-fonts",
            Self::SetupKythDevBox => "setup-kyth-dev-box",
            Self::AiDevStatus => "ai-dev-status",
            Self::AiDevSetup => "ai-dev-setup",
            Self::SetupWaydroid => "setup-waydroid",
            // The Hub confirms first (RecipeButton confirm), so it runs the
            // prompt-free variant; the interactive recipe stays for terminals.
            Self::RemoveWaydroid => "remove-waydroid-confirmed",
            Self::InstallVscode => "install-vscode",
            Self::InstallBoxbuddy => "install-boxbuddy",
            Self::InstallJetbrainsToolbox => "install-jetbrains-toolbox",
            Self::GamingMode => "gaming-mode",
            Self::BalancedMode => "balanced-mode",
            Self::HdrPerGame => "hdr-per-game",
            Self::EnableBpftune => "enable-bpftune",
            Self::DisableBpftune => "disable-bpftune",
            Self::InstallSteam => "install-steam",
            Self::InstallHeroic => "install-heroic",
            Self::InstallLutris => "install-lutris",
            Self::InstallBottles => "install-bottles",
            Self::InstallPrismlauncher => "install-prismlauncher",
            Self::InstallItch => "install-itch",
            Self::InstallEpicLauncher => "install-epic-launcher",
            Self::InstallBattlenet => "install-battlenet",
            Self::InstallEaApp => "install-ea-app",
            Self::InstallUbisoftConnect => "install-ubisoft-connect",
            Self::PreheatShaders => "preheat-shaders",
            Self::EnableObsCapture => "enable-obs-capture",
            Self::GameBoost => "game-boost",
            Self::ControllerCheck => "controller-check",
            Self::ExportSteamGames => "export-steam-games",
            Self::InstallObs => "install-obs",
            Self::InstallGpuScreenRecorder => "install-gpu-screen-recorder",
            Self::InstallGoverlay => "install-goverlay",
            Self::InstallMangojuice => "install-mangojuice",
            Self::InstallUmu => "install-umu",
            Self::InstallLact => "install-lact",
            Self::InstallPiper => "install-piper",
            Self::InstallSolaar => "install-solaar",
            Self::NvidiaStatus => "nvidia-status",
            Self::ListPresets => "list-presets",
            Self::SetupPrinter => "setup-printer",
            Self::EnrollSecureboot => "enroll-secureboot",
            Self::SystemAudit => "system-audit",
            Self::GamingAudit => "gaming-audit",
        }
    }
}

fn start_hub_action_job(action: HubAction) -> Result<HubActionLaunch, String> {
    let recipe = action.recipe();
    let argv = kyth_shared::system::just::command_for(recipe, &[])
        .ok_or_else(|| "Hub action is not allowlisted".to_string())?;
    kyth_shared::commands::normalize_command(&argv)
        .map_err(|_| "recipe produced an invalid command".to_string())?;
    let job = format!(
        "hub-action-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    let (job, cancel) = hub_action_jobs().start(&job, format!("Running {recipe}…"));
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
        let result = kyth_shared::system::process::run_bounded_command_cancel(
            command,
            timeout_for(JobTimeoutClass::HubAction),
            &cancel,
        );
        let (state, detail) = match result {
            Ok(output) => {
                let state = if output.status.success() {
                    "complete"
                } else {
                    "failed"
                };
                (
                    state.to_string(),
                    just_output_detail(&recipe_for_thread, &output),
                )
            }
            Err(error) => (
                "failed".to_string(),
                format!("Could not start {recipe_for_thread}: {error}"),
            ),
        };
        hub_action_jobs().finish(&job_for_thread, &state, detail);
    });
    Ok(HubActionLaunch {
        job,
        state: "running".into(),
        detail: format!("Running {recipe}…"),
    })
}

/// Start an Updates-page operation as a native Rust-managed job. The command
/// is always a fixed argv; `just` is intentionally not involved here. The
/// privileged safety helper remains the root boundary for upgrade policy and
/// boot-health recording, while Rust owns lifecycle, timeout, and UI output.
#[derive(Serialize)]
pub(crate) struct UpdateActionLaunch {
    pub(crate) job: String,
    pub(crate) state: String,
    pub(crate) detail: String,
}

fn start_update_job(
    job_slug: &str,
    operation: &str,
    argv: Vec<String>,
    timeout: Duration,
    slot: MutatingSlot,
) -> Result<UpdateActionLaunch, String> {
    kyth_shared::commands::normalize_command(&argv)
        .map_err(|_| "update produced an invalid command".to_string())?;
    // The slug (not the display label) owns the id: frontend reattach only
    // trusts `<prefix>-<nanos>` ids, so a label with spaces would strand the
    // job (and its Cancel) across a reload.
    let job = format!(
        "update-{}-{}",
        job_slug,
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    let (job, cancel) = update_jobs().start(&job, format!("{operation} is running…"));
    let job_for_thread = job.clone();
    let operation_for_thread = operation.to_string();
    std::thread::spawn(move || {
        // Held to the end of the job: the second mutating launch fails at
        // take_mutating_slot instead of racing this one.
        let _slot = slot;
        let mut command = Command::new(&argv[0]);
        command.args(&argv[1..]);
        let inherited = std::env::vars().collect::<std::collections::BTreeMap<_, _>>();
        let desktop = kyth_shared::commands::environment_for(
            kyth_shared::commands::EnvironmentPolicy::Desktop,
            &inherited,
        );
        command.env_clear().envs(desktop);
        if std::path::Path::new("/usr/bin/ksshaskpass").exists() {
            command.env("SUDO_ASKPASS", "/usr/bin/ksshaskpass");
        }
        let result =
            kyth_shared::system::process::run_bounded_command_cancel(command, timeout, &cancel);
        let (state, detail) = match result {
            Ok(output) => {
                let mut detail = String::from_utf8_lossy(&output.stdout).trim().to_string();
                let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
                if !stderr.is_empty() {
                    if !detail.is_empty() {
                        detail.push('\n');
                    }
                    detail.push_str(&stderr);
                }
                let detail: String = kyth_shared::system::process::redact_sensitive_text(
                    kyth_shared::system::process::strip_ansi(&detail).as_str(),
                )
                .chars()
                .rev()
                .take(1200)
                .collect::<String>()
                .chars()
                .rev()
                .collect();
                let state = if output.status.success() {
                    "complete"
                } else {
                    "failed"
                };
                let detail = if detail.is_empty() {
                    if output.status.success() {
                        format!("{operation_for_thread} complete.")
                    } else {
                        format!(
                            "{operation_for_thread} failed (exit code {}).",
                            output.status.code().unwrap_or(-1)
                        )
                    }
                } else {
                    detail
                };
                (state.to_string(), detail)
            }
            Err(error) => (
                "failed".to_string(),
                format!("{operation_for_thread} could not complete: {error}"),
            ),
        };
        update_jobs().finish(&job_for_thread, &state, detail);
    });
    Ok(UpdateActionLaunch {
        job,
        state: "running".into(),
        detail: format!("{operation} is running…"),
    })
}

#[tauri::command]
pub(crate) fn run_hub_action(action: HubAction) -> Result<HubActionLaunch, String> {
    start_hub_action_job(action)
}

fn update_store_status(store: &JobStore, job: String, not_found: &str) -> crate::InstallStatus {
    let (state, detail) = store.status(&job).unwrap_or((
        kyth_shared::system::jobs::STATE_UNKNOWN.into(),
        not_found.into(),
    ));
    crate::InstallStatus {
        id: job,
        state,
        detail,
    }
}

#[tauri::command]
pub(crate) fn hub_action_status(job: String) -> crate::InstallStatus {
    update_store_status(hub_action_jobs(), job, "Hub action job not found.")
}

/// Cancel a running Hub action: its recipe process is killed within one
/// poll tick and the job reads `cancelled` from then on.
#[tauri::command]
pub(crate) fn hub_action_cancel(job: String) -> crate::InstallStatus {
    hub_action_jobs().cancel(&job);
    update_store_status(hub_action_jobs(), job, "Hub action job not found.")
}

#[tauri::command]
pub(crate) fn bootc_upgrade() -> Result<UpdateActionLaunch, String> {
    if !std::path::Path::new("/usr/bin/kyth-safe-upgrade").exists() {
        return Err("The native KythOS update helper is not installed on this system.".to_string());
    }
    // Admission check like rollback/switch/apply below: kyth-safe-upgrade
    // takes the shared bootc lock for the whole stage, so refuse a second
    // mutating launch here instead of stacking two sudo prompts that
    // serialize anyway.
    let slot = take_mutating_slot()?;
    kyth_shared::system::bootc_guard::with_bootc_lock(|| Ok::<(), String>(()))?;
    start_stage_job(
        "stage",
        "Download and stage",
        vec!["sudo", "-A", "/usr/bin/kyth-safe-upgrade"]
            .into_iter()
            .map(String::from)
            .collect(),
        timeout_for(JobTimeoutClass::LongTransfer),
        slot,
    )
}

#[tauri::command]
pub(crate) fn bootc_rollback() -> Result<UpdateActionLaunch, String> {
    // Admission check on the shared bootc lock: the privileged helper takes
    // it for the whole rollback, so refuse a second mutating launch here
    // instead of stacking two sudo prompts that serialize anyway.
    let slot = take_mutating_slot()?;
    kyth_shared::system::bootc_guard::with_bootc_lock(|| Ok::<(), String>(()))?;
    start_update_job(
        "rollback",
        "Rollback",
        vec!["sudo", "-A", "/usr/bin/bootc", "rollback"]
            .into_iter()
            .map(String::from)
            .collect(),
        timeout_for(JobTimeoutClass::UpdateMutating),
        slot,
    )
}

#[tauri::command]
pub(crate) fn bootc_switch_branch(branch: String) -> Result<UpdateActionLaunch, String> {
    let channel = kyth_shared::system::bootc_policy::switch_channel_arg(&branch)
        .ok_or_else(|| "unknown channel".to_string())?;
    let operation = format!(
        "switch-{}",
        if channel == "stable" {
            "latest"
        } else {
            channel
        }
    );
    let mut argv = vec!["sudo", "-A", "/usr/bin/kyth-bootc-guard"]
        .into_iter()
        .map(String::from)
        .collect::<Vec<_>>();
    argv.push(operation);
    // Same admission check as rollback: kyth-bootc-guard takes the shared
    // lock for the whole switch.
    let slot = take_mutating_slot()?;
    kyth_shared::system::bootc_guard::with_bootc_lock(|| Ok::<(), String>(()))?;
    start_update_job(
        "switch",
        "Switch channel",
        argv,
        timeout_for(JobTimeoutClass::UpdateMutating),
        slot,
    )
}

#[tauri::command]
pub(crate) fn apply_staged() -> Result<UpdateActionLaunch, String> {
    if !std::path::Path::new("/usr/libexec/kyth-finalize-staged").exists() {
        return Err("The staged-update finalizer is not installed on this system.".to_string());
    }
    // Systemd's shutdown hook finalizes any raw staged deployment; the Hub
    // only requests the reboot here. Serialize that restart against other
    // bootc mutations so it cannot race an upgrade/switch.
    let slot = take_mutating_slot()?;
    kyth_shared::system::bootc_guard::with_bootc_lock(|| Ok::<(), String>(()))?;
    start_update_job(
        "apply",
        "Restart to apply staged update",
        vec!["sudo", "-A", "/usr/libexec/kyth-finalize-staged", "reboot"]
            .into_iter()
            .map(String::from)
            .collect(),
        timeout_for(JobTimeoutClass::UpdateMutating),
        slot,
    )
}

#[tauri::command]
pub(crate) fn update_job_status(job: String) -> crate::InstallStatus {
    update_store_status(update_jobs(), job, "Update job not found.")
}

/// Cancel a running update job: its process is killed within one poll tick
/// and the job reads `cancelled` from then on.
#[tauri::command]
pub(crate) fn update_job_cancel(job: String) -> crate::InstallStatus {
    update_jobs().cancel(&job);
    update_store_status(update_jobs(), job, "Update job not found.")
}

#[tauri::command]
pub(crate) fn branch_display_name(tag: Option<String>) -> String {
    kyth_shared::system::bootc_policy::branch_display_name(tag.as_deref())
}

#[tauri::command]
pub(crate) async fn pending_updates_summary() -> std::collections::HashMap<String, String> {
    tauri::async_runtime::spawn_blocking(
        kyth_shared::system::updates_unified::pending_updates_summary,
    )
    .await
    .unwrap_or_default()
}

#[tauri::command]
pub(crate) async fn update_status() -> UpdateStatusResponse {
    tauri::async_runtime::spawn_blocking(update_status_response)
        .await
        .unwrap_or_else(|_| UpdateStatusResponse {
            booted: None,
            staged: false,
            rollback: false,
            remote_digest: None,
            blocked_reason: Some("Could not read update status.".to_string()),
            retry_cmd: Some("bootc upgrade --check".to_string()),
            check_state: "error".to_string(),
            detail: "Could not read update status.".to_string(),
        })
}

fn update_status_response() -> UpdateStatusResponse {
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
pub(crate) async fn collect_availability(
    branch: Option<String>,
    use_cached: Option<bool>,
) -> AvailabilityStatusResponse {
    let status = tauri::async_runtime::spawn_blocking(move || {
        kyth_shared::system::update_availability::collect_availability(
            branch.as_deref(),
            use_cached.unwrap_or(true),
        )
    })
    .await
    .unwrap_or_else(
        |_| kyth_shared::system::update_availability::AvailabilityStatus {
            state: "error".to_string(),
            detail: "Could not check update availability.".to_string(),
            flatpak_count: 0,
            flatpak_detail: String::new(),
            staged: false,
            manifest_raw: String::new(),
            blocked_reason: "Could not check update availability.".to_string(),
        },
    );
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

/// Resolve the active channel without making the short-lived probe cache a
/// hard dependency. The fallback can query bootc, so keep it off the Tauri
/// command/UI thread just like the update probes above.
#[tauri::command]
pub(crate) async fn current_update_channel() -> Option<String> {
    tauri::async_runtime::spawn_blocking(kyth_shared::system::bootc::current_branch)
        .await
        .ok()
        .flatten()
}

#[derive(Serialize)]
pub(crate) struct UpdateHealthResponse {
    pub(crate) status: String,
    pub(crate) pending_digest: String,
    pub(crate) last_healthy_digest: String,
    pub(crate) failures: i64,
    pub(crate) quarantined: usize,
    pub(crate) detail: String,
}

fn native_health_fallback() -> Option<(String, String, String, i64)> {
    // Prefer the same disk cache used by the rest of the Hub, but recover on
    // systems whose probe service has not populated it yet. This is still a
    // bounded native read and runs inside update_health's blocking worker.
    let status_data = kyth_shared::system::probe::read_section("bootc-status-data")
        .or_else(kyth_shared::system::bootc_query::fetch_status_data)?;
    let digest = kyth_shared::system::registry::booted_image_digest(&status_data)?;
    let os_release = std::fs::read_to_string("/usr/lib/os-release")
        .or_else(|_| std::fs::read_to_string("/etc/os-release"))
        .ok()?;
    let identity_ok = os_release
        .lines()
        .any(|line| line.trim() == "ID=kythos" || line.trim() == "ID=\"kythos\"");
    let runtime = kyth_shared::system::boot_runtime::boot_runtime_checks_with_deadline(
        std::time::Duration::from_secs(5),
        std::time::Duration::from_millis(100),
    );
    let mut failures = runtime
        .iter()
        .filter(|check| !check.passed)
        .map(|check| format!("{}: {}", check.name, check.detail))
        .collect::<Vec<_>>();
    if !identity_ok {
        failures.push("KythOS identity: /usr/lib/os-release is not ID=kythos".to_string());
    }
    if failures.is_empty() {
        Some((
            "healthy".to_string(),
            format!("Native boot checks passed for {digest}; no persistent boot-health record was available."),
            digest,
            0,
        ))
    } else {
        let count = failures.len() as i64;
        Some((
            "unhealthy".to_string(),
            format!("Native boot checks failed: {}", failures.join("; ")),
            digest,
            count,
        ))
    }
}

fn update_health_response() -> UpdateHealthResponse {
    let state = kyth_shared::system::boot_health::read_default_state();
    if state.status == "unknown"
        && state.current_digest.is_empty()
        && state.last_healthy_digest.is_empty()
        && state.updated_at == 0
    {
        if let Some((status, detail, digest, failures)) = native_health_fallback() {
            // The live booted digest is the digest under evaluation
            // (pending), not a known-good one: only a passing native
            // check may claim it as last-healthy, and the failure count
            // is the failed native checks — not the empty record's zero.
            let last_healthy_digest = if status == "healthy" {
                digest.clone()
            } else {
                String::new()
            };
            return UpdateHealthResponse {
                status,
                pending_digest: digest,
                last_healthy_digest,
                failures,
                quarantined: state.quarantined.len(),
                detail,
            };
        }
    }
    let invariants = state.invariants();
    let detail = if invariants.is_empty() {
        if state.status == "unknown" {
            "Boot health has not been recorded yet; native checks could not establish a live result.".to_string()
        } else {
            format!(
                "Boot health is {} · {} quarantined digest(s).",
                state.status,
                state.quarantined.len()
            )
        }
    } else {
        format!(
            "Boot health state needs attention: {}",
            invariants.join(", ")
        )
    };
    UpdateHealthResponse {
        status: state.status,
        pending_digest: state.pending_digest,
        last_healthy_digest: state.last_healthy_digest,
        failures: state.failures,
        quarantined: state.quarantined.len(),
        detail,
    }
}

#[tauri::command]
pub(crate) async fn update_health() -> UpdateHealthResponse {
    tauri::async_runtime::spawn_blocking(update_health_response)
        .await
        .unwrap_or_else(|_| UpdateHealthResponse {
            status: "unknown".to_string(),
            pending_digest: String::new(),
            last_healthy_digest: String::new(),
            failures: 0,
            quarantined: 0,
            detail: "Native boot-health check could not complete.".to_string(),
        })
}

#[cfg(test)]
mod tests {
    use super::HubAction;

    #[test]
    fn hub_action_deserializes_allowlisted_recipe() {
        let action: HubAction =
            serde_json::from_str("\"enroll-secureboot\"").expect("known action");
        assert_eq!(action.recipe(), "enroll-secureboot");
    }

    #[test]
    fn hub_action_rejects_unknown_recipe() {
        let result = serde_json::from_str::<HubAction>("\"run-arbitrary-command\"");
        assert!(result.is_err());
    }

    #[test]
    fn stage_marker_parses_pct_phase_and_detail() {
        let snapshot = super::parse_stage_marker(
            "KYTH_STAGE_PROGRESS pct=42 phase=download detail=Downloading layer 12 of 39",
        )
        .expect("marker parses");
        assert_eq!(snapshot.pct, 42);
        assert_eq!(snapshot.phase, "download");
        assert_eq!(snapshot.detail, "Downloading layer 12 of 39");
        assert!(snapshot.active);
    }

    #[test]
    fn stage_marker_rejects_non_markers_and_caps_pct() {
        assert!(super::parse_stage_marker("Downloading layer 12 of 39").is_none());
        let snapshot = super::parse_stage_marker("KYTH_STAGE_PROGRESS pct=200 phase=install")
            .expect("marker parses");
        assert_eq!(snapshot.pct, 99);
        assert_eq!(snapshot.detail, "Installing the staged image…");
    }

    #[test]
    fn stage_line_reader_caps_unterminated_lines_and_continues() {
        let input = format!("{}\nnext\n", "x".repeat(1024));
        let mut reader = std::io::Cursor::new(input.into_bytes());
        let mut line = Vec::new();
        assert_eq!(
            super::read_stage_line(&mut reader, &mut line, 32).unwrap(),
            Some(true)
        );
        assert_eq!(line.len(), 32);
        assert_eq!(
            super::read_stage_line(&mut reader, &mut line, 32).unwrap(),
            Some(false)
        );
        assert_eq!(String::from_utf8_lossy(&line), "next\n");
        assert_eq!(
            super::read_stage_line(&mut reader, &mut line, 32).unwrap(),
            None
        );
    }

    #[test]
    fn bounded_stderr_capture_drains_past_its_memory_limit() {
        let input = vec![b'x'; 128];
        let mut reader = std::io::Cursor::new(input.clone());
        let captured = super::collect_bounded_output(&mut reader, 16).unwrap();
        assert_eq!(reader.position(), input.len() as u64);
        assert_eq!(&captured[..16], &input[..16]);
        assert!(captured.ends_with(b"\n...[truncated]"));
    }

    #[test]
    fn stage_merge_never_moves_the_bar_backwards() {
        let current = super::StageProgressSnapshot {
            pct: 60,
            phase: "download".into(),
            detail: "Downloading layer 20 of 39".into(),
            active: true,
        };
        let stale = super::StageProgressSnapshot {
            pct: 40,
            phase: "download".into(),
            detail: "Downloading layer 12 of 39".into(),
            active: true,
        };
        assert_eq!(super::merge_stage_snapshot(&current, stale).pct, 60);
        let advanced = super::StageProgressSnapshot {
            pct: 61,
            ..current.clone()
        };
        assert_eq!(super::merge_stage_snapshot(&current, advanced).pct, 61);
    }

    #[test]
    fn mutating_slot_rejects_a_second_launch_until_released() {
        let slot = super::take_mutating_slot().expect("first launch takes the slot");
        assert!(
            super::take_mutating_slot().is_err(),
            "double-click / second tab must fail fast, not spawn a second sudo job"
        );
        drop(slot);
        // The is_ok temporary drops at the end of the assert, releasing
        // the slot; belt-and-braces reset keeps later tests independent.
        assert!(
            super::take_mutating_slot().is_ok(),
            "finished job releases the slot"
        );
        super::UPDATE_MUTATING.store(false, std::sync::atomic::Ordering::SeqCst);
    }
}
