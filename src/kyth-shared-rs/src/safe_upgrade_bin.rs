use std::io::Read;
use std::os::unix::process::CommandExt;
use std::process::Stdio;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const REQUIRED_FREE_BYTES: u64 = 2 * 1024 * 1024 * 1024;
const BOOT_FREE_MIN_BYTES: u64 = 500 * 1024 * 1024;
const VAR_CACHE_FREE_MIN_BYTES: u64 = 500 * 1024 * 1024;
const TERM_GRACE: Duration = Duration::from_secs(10);
const BOOTC_TIMEOUT: Duration = Duration::from_secs(3600);
const DEFAULT_CONFIG: &str = "/etc/kyth/auto-update.toml";

/// Set by the SIGTERM watcher thread. When true, the in-flight `bootc`
/// child has been (or is being) torn down and no staged state may be
/// recorded: a terminated upgrade must never look staged.
static CANCELLED: AtomicBool = AtomicBool::new(false);

fn now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64
}

fn rollout_ring() -> String {
    std::fs::read_to_string(DEFAULT_CONFIG)
        .ok()
        .and_then(|text| text.parse::<toml::Value>().ok())
        .and_then(|value| value.get("auto_update").cloned().or(Some(value)))
        .and_then(|value| {
            value
                .get("rollout_ring")
                .and_then(toml::Value::as_str)
                .map(str::to_owned)
        })
        .unwrap_or_else(|| "follow-image".into())
}

fn free_bytes(path: &str) -> Option<u64> {
    let stat = rustix::fs::statvfs(path).ok()?;
    Some(stat.f_bavail.saturating_mul(stat.f_frsize))
}

fn check_free(path: &str, min: u64) -> Result<(), String> {
    if let Some(free) = free_bytes(path) {
        if free < min {
            return Err(format!(
                "Not enough free disk space on {path}: {} MiB free, need {} MiB",
                free / (1024 * 1024),
                min / (1024 * 1024)
            ));
        }
    }
    Ok(())
}

/// Best-effort removal of dracut scratch left under `/var/tmp` when an
/// upgrade fails or is terminated. dracut runs with `--tmpdir /var/tmp`;
/// an interrupted build can leave multi-hundred-MB stage directories behind.
fn scrub_dracut_scratch() {
    let Ok(entries) = std::fs::read_dir("/var/tmp") else {
        return;
    };
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        if !(name.starts_with("dracut.") || name.starts_with(".dracut")) {
            continue;
        }
        let path = entry.path();
        if path.is_dir() {
            let _ = std::fs::remove_dir_all(&path);
        } else {
            let _ = std::fs::remove_file(&path);
        }
    }
}

fn output_text(output: &std::process::Output) -> String {
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    kyth_shared::system::process::redact_sensitive_text(
        kyth_shared::system::process::strip_ansi(text.trim()).as_str(),
    )
    .chars()
    .take(2000)
    .collect()
}

/// Watch for SIGTERM on a dedicated thread: libc-level `sigwait` needs no
/// extra crate. The mask is installed before the upgrade child spawns so the
/// watcher thread — not the default disposition — owns delivery.
fn arm_sigterm_forwarder() {
    unsafe {
        let mut set: libc::sigset_t = std::mem::zeroed();
        libc::sigemptyset(&mut set);
        libc::sigaddset(&mut set, libc::SIGTERM);
        libc::pthread_sigmask(libc::SIG_BLOCK, &set, std::ptr::null_mut());
    }
    std::thread::spawn(|| unsafe {
        let mut set: libc::sigset_t = std::mem::zeroed();
        libc::sigemptyset(&mut set);
        libc::sigaddset(&mut set, libc::SIGTERM);
        let mut signo = 0;
        if libc::sigwait(&set, &mut signo) == 0 && signo == libc::SIGTERM {
            CANCELLED.store(true, Ordering::SeqCst);
        }
    });
}

fn drain_pipe(pipe: &mut Option<impl Read + Send + 'static>) -> Vec<u8> {
    let mut buf = Vec::new();
    if let Some(pipe) = pipe.as_mut() {
        let _ = pipe.read_to_end(&mut buf);
    }
    buf
}

/// Run `bootc upgrade` as its own process group so termination reaches
/// forked grandchildren. On SIGTERM the group gets SIGTERM, up to 10s to
/// exit gracefully, then SIGKILL; the caller reports failure and records
/// nothing.
fn run_bootc_child() -> Result<std::process::Output, String> {
    let mut command = std::process::Command::new("/usr/bin/bootc");
    command
        .arg("upgrade")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    command.process_group(0);
    let mut child = command
        .spawn()
        .map_err(|error| format!("bootc upgrade could not start: {error}"))?;
    // Drain pipes on helper threads: bootc is chatty and a full pipe would
    // wedge the child while we poll below.
    let mut stdout = child.stdout.take();
    let mut stderr = child.stderr.take();
    let stdout_reader = std::thread::spawn(move || drain_pipe(&mut stdout));
    let stderr_reader = std::thread::spawn(move || drain_pipe(&mut stderr));
    let started = std::time::Instant::now();
    let mut term_at: Option<std::time::Instant> = None;
    loop {
        if let Some(status) = child
            .try_wait()
            .map_err(|error| format!("bootc upgrade could not be reaped: {error}"))?
        {
            let stdout = stdout_reader.join().unwrap_or_default();
            let stderr = stderr_reader.join().unwrap_or_default();
            if CANCELLED.load(Ordering::SeqCst) {
                scrub_dracut_scratch();
                return Err(
                    "bootc upgrade was terminated and did not complete; nothing was staged"
                        .to_string(),
                );
            }
            return Ok(std::process::Output {
                status,
                stdout,
                stderr,
            });
        }
        if CANCELLED.load(Ordering::SeqCst) && term_at.is_none() {
            term_at = Some(std::time::Instant::now());
            let pgid = child.id() as libc::pid_t;
            unsafe {
                libc::killpg(pgid, libc::SIGTERM);
            }
        }
        if let Some(since_term) = term_at {
            if since_term.elapsed() > TERM_GRACE {
                let pgid = child.id() as libc::pid_t;
                unsafe {
                    libc::killpg(pgid, libc::SIGKILL);
                }
                let _ = child.wait();
                let _ = stdout_reader.join();
                let _ = stderr_reader.join();
                scrub_dracut_scratch();
                return Err(
                    "bootc upgrade was terminated and did not complete; nothing was staged"
                        .to_string(),
                );
            }
            std::thread::sleep(Duration::from_millis(25));
            continue;
        }
        if started.elapsed() > BOOTC_TIMEOUT {
            kyth_shared::system::process::kill_process_group(&mut child);
            let _ = stdout_reader.join();
            let _ = stderr_reader.join();
            scrub_dracut_scratch();
            return Err("bootc upgrade timed out; retry later".into());
        }
        std::thread::sleep(Duration::from_millis(25));
    }
}

fn run_upgrade() -> Result<String, String> {
    check_free("/sysroot", REQUIRED_FREE_BYTES)?;
    check_free("/boot", BOOT_FREE_MIN_BYTES)?;
    check_free("/var/tmp", REQUIRED_FREE_BYTES)?;
    kyth_shared::system::bootc_guard::with_bootc_lock(|| match run_bootc_child() {
        Ok(output) if output.status.success() => Ok(output_text(&output)),
        Ok(output) => {
            scrub_dracut_scratch();
            Err(output_text(&output))
        }
        Err(error) => {
            scrub_dracut_scratch();
            Err(error)
        }
    })
}

fn upgrade() -> Result<String, String> {
    if !rustix::process::getuid().is_root() {
        return Err("kyth-safe-upgrade must run as root".into());
    }
    arm_sigterm_forwarder();
    let status = kyth_shared::system::bootc_query::fetch_status_data()
        .ok_or_else(|| "Could not determine the booted image status".to_string())?;
    let reference = kyth_shared::system::bootc_query::image_reference_from_status(&status)
        .ok_or_else(|| "Could not determine the booted image reference".to_string())?;
    let ring = rollout_ring();
    if let Some(reason) = kyth_shared::system::boot_health::rollout_policy_reason(&reference, &ring)
    {
        return Err(format!("Update blocked by rollout policy: {reason}"));
    }
    // Do not make staging depend on a second registry client. GHCR metadata
    // probes can time out while bootc itself can still reach the image; bootc
    // is the authoritative fetcher for the mutating update path.
    let state = kyth_shared::system::boot_health::read_default_state();
    let booted = kyth_shared::system::bootc_query::image_digest_from_status(&status, "booted");
    let staged = kyth_shared::system::bootc_query::image_digest_from_status(&status, "staged");
    if let Some(reason) = staged
        .as_deref()
        .and_then(|digest| kyth_shared::system::boot_health::quarantine_reason(&state, digest))
    {
        return Err(format!("Update blocked: {reason}"));
    }
    if kyth_shared::system::bootc_query::active_operation().is_some() {
        return Err("Another bootc upgrade is in progress; retry later".into());
    }
    let detail = run_upgrade().map_err(|error| {
        scrub_dracut_scratch();
        error
    })?;
    if CANCELLED.load(Ordering::SeqCst) {
        scrub_dracut_scratch();
        return Err(
            "bootc upgrade was terminated and did not complete; nothing was staged".to_string(),
        );
    }
    let after = kyth_shared::system::bootc_query::fetch_status_data();
    let staged_after = after.as_ref().and_then(|data| {
        kyth_shared::system::bootc_query::image_digest_from_status(data, "staged")
    });
    let staged_quarantine_reason = staged_after.as_deref().and_then(|digest| {
        let state = kyth_shared::system::boot_health::read_default_state();
        kyth_shared::system::boot_health::quarantine_reason(&state, digest)
    });
    let post_upgrade = kyth_shared::system::safe_upgrade_policy::validate_post_upgrade_state(
        booted.as_deref(),
        after
            .as_ref()
            .and_then(|data| {
                kyth_shared::system::bootc_query::image_digest_from_status(data, "booted")
            })
            .as_deref(),
        staged_after.as_deref(),
        staged_quarantine_reason.as_deref(),
    )?;
    let Some(staged_digest) = post_upgrade else {
        return Ok(if detail.is_empty() {
            "KythOS is already running the latest allowed digest.".into()
        } else {
            detail
        });
    };
    let coordinator = kyth_shared::system::update_coordinator::UpdateCoordinator::new(
        kyth_shared::system::boot_health::DEFAULT_STATE_PATH,
    );
    coordinator
        .record_staged(
            &staged_digest,
            kyth_shared::system::boot_health::image_ring(&reference).unwrap_or(&ring),
            now(),
        )
        .map_err(|error| format!("Could not persist staged update state: {error}"))?;
    check_free("/var/cache", VAR_CACHE_FREE_MIN_BYTES)?;
    let finalized = kyth_shared::system::boot_finalize::finalize_staged(false)?;
    Ok(if finalized.is_empty() {
        if detail.is_empty() {
            "Update staged and promoted to the next boot.".into()
        } else {
            detail
        }
    } else {
        finalized
    })
}

fn main() -> std::process::ExitCode {
    if std::env::args().nth(1).is_some() {
        eprintln!("kyth-safe-upgrade accepts no arguments");
        return std::process::ExitCode::from(64);
    }
    match upgrade() {
        Ok(detail) => {
            if !detail.is_empty() {
                println!("{detail}");
            }
            std::process::ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{error}");
            std::process::ExitCode::from(1)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn space_minimums_match_policy() {
        assert_eq!(BOOT_FREE_MIN_BYTES / (1024 * 1024), 500);
        assert_eq!(REQUIRED_FREE_BYTES / (1024 * 1024), 2048);
        assert_eq!(VAR_CACHE_FREE_MIN_BYTES / (1024 * 1024), 500);
    }

    #[test]
    fn term_grace_is_ten_seconds() {
        assert_eq!(TERM_GRACE, Duration::from_secs(10));
    }
}
