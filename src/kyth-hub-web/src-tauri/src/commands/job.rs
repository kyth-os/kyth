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
        let (state, detail) = on_done(result);
        finish_job(job, &state, detail);
    });
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
