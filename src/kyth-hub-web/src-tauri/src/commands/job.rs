//! Shared background-job runner for bounded shell/argv actions that take too
//! long to block a Tauri command — installs, container lifecycle steps,
//! recipe-adjacent fixes. One job store, one `job_status` poll command;
//! every domain module (`security`, `gaming`) gets its own `start_job`
//! prefix so job ids stay readable in logs, but the store and polling
//! contract are identical everywhere. Reports running/complete/failed, not
//! a live percentage — see `security_container`'s module doc for why.

use std::process::{Command, Output};
use std::sync::atomic::AtomicBool;
use std::sync::{Arc, OnceLock};
use std::time::Duration;

use kyth_shared::system::jobs::JobStore;

static JOBS: OnceLock<JobStore> = OnceLock::new();

fn jobs() -> &'static JobStore {
    JOBS.get_or_init(JobStore::default)
}

/// Process-wide single-flight for flatpak mutations. Flatpak serializes
/// transactions per installation with its own lock, so two Hub actions
/// that mutate at once (an install from the Apps page while a host-tool
/// install runs from the Security grid, a double-started update) make one
/// of them fail with a lock error that reads as a random failure. The
/// system-update commands have `take_mutating_slot`; flatpak operations
/// across main.rs, security, and gaming share this one slot instead —
/// whichever domain starts first owns it until its job finishes.
static FLATPAK_MUTATING: AtomicBool = AtomicBool::new(false);

/// RAII handle for the flatpak mutation slot: dropping it frees the slot,
/// including on panic/early-return paths inside a job worker.
#[derive(Debug)]
pub(crate) struct FlatpakSlot;

impl Drop for FlatpakSlot {
    fn drop(&mut self) {
        FLATPAK_MUTATING.store(false, std::sync::atomic::Ordering::SeqCst);
    }
}

/// Claim the flatpak mutation slot, or explain which action must finish
/// first. Callers claim BEFORE starting their job and move the guard into
/// the worker so it is held for the job's whole life.
pub(crate) fn take_flatpak_slot() -> Result<FlatpakSlot, String> {
    FLATPAK_MUTATING
        .compare_exchange(
            false,
            true,
            std::sync::atomic::Ordering::SeqCst,
            std::sync::atomic::Ordering::SeqCst,
        )
        .map(|_| FlatpakSlot)
        .map_err(|_| {
            "Another app install, update, or removal is already in progress. \
             Wait for it to finish before starting another."
                .to_string()
        })
}

/// Process-wide single-flight for MUTATING Hub actions (`run_hub_action`:
/// installs, firmware updates, mode switches, enrollments). Two recipes
/// running at once stack sudo prompts and race on the same system state —
/// a hub-action firmware update could even run concurrently with a
/// slot-held bootc stage from the Updates page. Read-only recipes
/// (status/audit/check listings) never claim this slot, so a long install
/// cannot block a status read; the classification lives on the action
/// enum in updates.rs and defaults to mutating.
static HUB_ACTION_MUTATING: AtomicBool = AtomicBool::new(false);

/// RAII handle for the hub-action slot: dropping it frees the slot,
/// including on panic/early-return paths inside a job worker.
#[derive(Debug)]
pub(crate) struct HubActionSlot;

impl Drop for HubActionSlot {
    fn drop(&mut self) {
        HUB_ACTION_MUTATING.store(false, std::sync::atomic::Ordering::SeqCst);
    }
}

/// Claim the hub-action mutation slot, or explain which action must
/// finish first. Callers claim BEFORE starting their job and move the
/// guard into the worker so it is held for the job's whole life.
pub(crate) fn take_hub_action_slot() -> Result<HubActionSlot, String> {
    HUB_ACTION_MUTATING
        .compare_exchange(
            false,
            true,
            std::sync::atomic::Ordering::SeqCst,
            std::sync::atomic::Ordering::SeqCst,
        )
        .map(|_| HubActionSlot)
        .map_err(|_| {
            "Another Hub action is already in progress. \
             Wait for it to finish before starting another."
                .to_string()
        })
}

/// Ensure the per-user Flathub remote exists before an install. Runs
/// inside the tracked, cancellable workflow (never on a command thread):
/// `flatpak install flathub …` fails outright when the remote is missing,
/// which used to make installs from one page fail while pages that did
/// this step self-healed.
pub(crate) fn ensure_flathub_user_remote(cancel: &AtomicBool) -> Result<(), String> {
    let mut command = Command::new("flatpak");
    command.args([
        "remote-add",
        "--user",
        "--if-not-exists",
        "flathub",
        "https://dl.flathub.org/repo/flathub.flatpakrepo",
    ]);
    let output = kyth_shared::system::process::run_bounded_command_cancel(
        command,
        Duration::from_secs(60),
        cancel,
    )
    .map_err(|error| match error.kind() {
        std::io::ErrorKind::TimedOut => "Flathub setup took too long and was stopped.".to_string(),
        std::io::ErrorKind::Interrupted => "Flathub setup was cancelled.".to_string(),
        _ => format!("Could not start Flathub setup: {error}"),
    })?;
    if output.status.success() {
        Ok(())
    } else {
        Err(failure_detail("Flathub setup", &output))
    }
}

pub(crate) fn new_job_id(prefix: &str) -> String {
    format!(
        "{prefix}-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    )
}

pub(crate) fn start_job(prefix: &str, pending: &str) -> Result<String, String> {
    let job = new_job_id(prefix);
    let (job, _) = jobs().start(&job, pending.to_string());
    Ok(job)
}

/// Cancellation flag for a tracked job, so workers can hand it to the
/// cancellable runner. `None` for unknown or expired jobs.
pub(crate) fn cancel_flag(job: &str) -> Option<Arc<AtomicBool>> {
    jobs().cancel_flag(job)
}

fn finish_job(job: String, state: &str, detail: String) {
    jobs().finish(&job, state, detail);
}

fn install_status(job: String, fallback: &str) -> crate::InstallStatus {
    let (state, detail) = jobs().status(&job).unwrap_or((
        kyth_shared::system::jobs::STATE_UNKNOWN.into(),
        fallback.into(),
    ));
    crate::InstallStatus {
        id: job,
        state,
        detail,
    }
}

#[tauri::command]
pub(crate) fn job_status(job: String) -> crate::InstallStatus {
    install_status(job, "Job not found.")
}

/// Cancel a running job: its child process is killed within one poll tick
/// and the job reads `cancelled` from then on. Terminal or unknown jobs
/// report their current status unchanged.
#[tauri::command]
pub(crate) fn cancel_job(job: String) -> crate::InstallStatus {
    jobs().cancel(&job);
    install_status(job, "Job not found.")
}

/// Same truncation/direction convention as the Hub action output helper:
/// keep the tail of combined stdout+stderr, since that's where the actual
/// error usually is in apt/flatpak/distrobox output.
pub(crate) fn failure_detail(action: &str, output: &Output) -> String {
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
    let tail: String = text
        .chars()
        .rev()
        .take(500)
        .collect::<String>()
        .chars()
        .rev()
        .collect();
    if tail.trim().is_empty() {
        match output.status.code() {
            Some(code) => format!("{action} failed (exit {code})."),
            None => format!("{action} stopped before it could complete."),
        }
    } else {
        format!("{action} failed — {}", tail.trim())
    }
}

fn askpass_env(command: &mut Command) {
    if std::path::Path::new("/usr/bin/ksshaskpass").exists() {
        command.env("SUDO_ASKPASS", "/usr/bin/ksshaskpass");
    }
}

pub(crate) fn spawn_argv_job(
    job: String,
    argv: Vec<String>,
    timeout: Duration,
    on_done: impl FnOnce(Result<Output, std::io::Error>) -> (String, String) + Send + 'static,
) {
    if argv.is_empty() {
        // Indexing argv[0] below would panic inside the worker thread,
        // leaving the job stuck on "running" for every poller. Fail it
        // on the caller so the status contract still resolves.
        finish_job(job, "failed", "Job has no command to run.".to_string());
        return;
    }
    // The flag is registered by start_job; a detached always-false flag
    // keeps the worker correct if the entry already expired.
    let cancel = cancel_flag(&job).unwrap_or_else(|| Arc::new(AtomicBool::new(false)));
    std::thread::spawn(move || {
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let mut command = Command::new(&argv[0]);
            command.args(&argv[1..]);
            // Sudo children never inherit the caller environment: clear it and
            // keep only the minimal desktop set via the shared sanitizer, then
            // set the askpass helper explicitly. No `-E` passthrough.
            if argv
                .first()
                .is_some_and(|program| program == "sudo" || program.ends_with("/sudo"))
            {
                let inherited = std::env::vars().collect::<std::collections::BTreeMap<_, _>>();
                let desktop = kyth_shared::commands::environment_for(
                    kyth_shared::commands::EnvironmentPolicy::Desktop,
                    &inherited,
                );
                command.env_clear().envs(desktop);
            }
            askpass_env(&mut command);
            let result =
                kyth_shared::system::process::run_bounded_command_cancel(command, timeout, &cancel);
            on_done(result)
        }));
        let (state, detail) = result.unwrap_or_else(|_| {
            (
                "failed".into(),
                "Background command worker panicked.".into(),
            )
        });
        finish_job(job, &state, detail);
    });
}

pub(crate) fn update_job(job: &str, detail: &str) {
    jobs().update_detail(job, detail.to_string());
}

/// Run a multi-step cancellable workflow in the shared tracked-job store.
/// The task receives its id (to publish phase details) and cancellation flag;
/// a cancelled job remains terminal even if the worker returns later.
pub(crate) fn spawn_task_job(
    job: String,
    task: impl FnOnce(String, Arc<AtomicBool>) -> (String, String) + Send + 'static,
) {
    let cancel = cancel_flag(&job).unwrap_or_else(|| Arc::new(AtomicBool::new(false)));
    std::thread::spawn(move || {
        let (state, detail) =
            std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| task(job.clone(), cancel)))
                .unwrap_or_else(|_| ("failed".into(), "Background task worker panicked.".into()));
        finish_job(job, &state, detail);
    });
}

/// [`spawn_task_job`] with a job-level deadline, for workflows whose
/// steps are individually bounded but whose SEQUENCE is not (the
/// dev-tools wizard chains 1800s + 1800s + N×600s bounded steps, so the
/// whole job could previously run for ~90 minutes with nothing but the
/// user's Cancel to stop it).
///
/// The deadline is enforced by a watchdog thread: when it passes with
/// the job still running, the watchdog trips the job's cancellation flag
/// — tasks poll it in their bounded subprocess steps, so they abort
/// promptly — and publishes the terminal timeout failure itself, so
/// pollers stop waiting even if the task is wedged in a step that never
/// checks the flag (this process cannot kill another thread). A task
/// that ignores the flag and later finishes anyway overwrites the
/// timeout verdict with its own genuine outcome via the store's normal
/// finish path; deadline callers should treat the bound as
/// abort-and-report, not kill -9.
pub(crate) fn spawn_task_job_with_deadline(
    job: String,
    deadline: Duration,
    task: impl FnOnce(String, Arc<AtomicBool>) -> (String, String) + Send + 'static,
) {
    let watchdog_job = job.clone();
    spawn_task_job(job, task);
    std::thread::spawn(move || {
        std::thread::sleep(deadline);
        if jobs()
            .status(&watchdog_job)
            .is_some_and(|(state, _)| state == kyth_shared::system::jobs::STATE_RUNNING)
        {
            if let Some(cancel) = cancel_flag(&watchdog_job) {
                cancel.store(true, std::sync::atomic::Ordering::SeqCst);
            }
            finish_job(
                watchdog_job,
                "failed",
                "Task took too long and was stopped.".to_string(),
            );
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn flatpak_slot_is_single_flight_until_dropped() {
        let first = take_flatpak_slot().expect("first claim succeeds");
        let second = take_flatpak_slot();
        assert!(
            second.is_err(),
            "a second flatpak mutation must be rejected while one runs"
        );
        assert!(second.unwrap_err().contains("already in progress"));
        drop(first);
        assert!(
            take_flatpak_slot().is_ok(),
            "dropping the guard frees the slot"
        );
    }

    #[test]
    fn task_job_publishes_phase_and_respects_cancellation() {
        let job = new_job_id("test-task");
        let (job, _) = jobs().start(&job, "pending".to_string());
        let (phase_tx, phase_rx) = std::sync::mpsc::channel();
        let (continue_tx, continue_rx) = std::sync::mpsc::channel();
        spawn_task_job(job.clone(), move |worker_job, _cancel| {
            update_job(&worker_job, "Setting up Flathub…");
            phase_tx.send(()).unwrap();
            continue_rx.recv().unwrap();
            ("complete".into(), "installed".into())
        });

        phase_rx.recv_timeout(Duration::from_secs(2)).unwrap();
        assert_eq!(
            jobs().status(&job),
            Some(("running".into(), "Setting up Flathub…".into()))
        );
        assert!(jobs().cancel(&job));
        continue_tx.send(()).unwrap();
        assert_eq!(
            jobs().status(&job),
            Some(("cancelled".into(), "Cancelled.".into()))
        );
    }

    #[test]
    fn hub_action_slot_is_single_flight_until_dropped() {
        let first = take_hub_action_slot().expect("first claim succeeds");
        let second = take_hub_action_slot();
        assert!(
            second.is_err(),
            "a second mutating hub action must be rejected while one runs"
        );
        assert!(second.unwrap_err().contains("already in progress"));
        drop(first);
        assert!(
            take_hub_action_slot().is_ok(),
            "dropping the guard frees the slot"
        );
    }

    #[test]
    fn task_job_deadline_fails_a_task_that_ignores_cancellation() {
        let job = new_job_id("test-deadline");
        let (job, cancel) = jobs().start(&job, "pending".to_string());
        let (release_tx, release_rx) = std::sync::mpsc::channel::<()>();
        let watchdog_job = job.clone();
        spawn_task_job_with_deadline(
            job,
            Duration::from_millis(50),
            move |_worker_job, _cancel| {
                // Park past the deadline without ever polling the flag:
                // the watchdog must still resolve the job for pollers.
                let _ = release_rx.recv_timeout(Duration::from_secs(30));
                ("complete".into(), "finished late".into())
            },
        );

        let deadline_at = std::time::Instant::now() + Duration::from_secs(5);
        loop {
            let status = jobs().status(&watchdog_job).expect("job stays tracked");
            if status.0 == "failed" {
                assert!(
                    status.1.contains("took too long"),
                    "deadline failure explains itself: {}",
                    status.1
                );
                break;
            }
            assert!(
                std::time::Instant::now() < deadline_at,
                "deadline never fired; job still {status:?}"
            );
            std::thread::sleep(Duration::from_millis(5));
        }
        assert!(
            cancel.load(std::sync::atomic::Ordering::SeqCst),
            "the watchdog trips the cancellation flag so polling steps abort"
        );
        release_tx.send(()).unwrap();
    }

    #[test]
    fn task_job_with_deadline_lets_a_fast_task_finish_untouched() {
        let job = new_job_id("test-deadline-fast");
        let (job, _) = jobs().start(&job, "pending".to_string());
        spawn_task_job_with_deadline(job.clone(), Duration::from_secs(30), |_job, _cancel| {
            ("complete".into(), "done".into())
        });

        let deadline_at = std::time::Instant::now() + Duration::from_secs(2);
        loop {
            if jobs()
                .status(&job)
                .is_some_and(|(state, _)| state == "complete")
            {
                break;
            }
            assert!(
                std::time::Instant::now() < deadline_at,
                "job stayed running"
            );
            std::thread::sleep(Duration::from_millis(5));
        }
    }

    #[test]
    fn empty_argv_fails_the_job_without_spawning() {
        let job = new_job_id("test-empty");
        let (job, _) = jobs().start(&job, "pending".to_string());
        spawn_argv_job(job.clone(), vec![], Duration::from_secs(5), |_| {
            panic!("empty argv must never reach the worker")
        });
        let (state, _) = jobs().status(&job).expect("job should resolve");
        assert_eq!(state, "failed");
    }

    #[test]
    fn panicking_task_fails_instead_of_leaving_job_running() {
        let job = new_job_id("test-panic");
        let (job, _) = jobs().start(&job, "pending".to_string());
        spawn_task_job(job.clone(), |_worker_job, _cancel| {
            panic!("simulated worker panic")
        });

        let deadline = std::time::Instant::now() + Duration::from_secs(2);
        loop {
            if jobs()
                .status(&job)
                .is_some_and(|(state, _)| state == "failed")
            {
                break;
            }
            assert!(std::time::Instant::now() < deadline, "job stayed running");
            std::thread::sleep(Duration::from_millis(5));
        }
    }
}
