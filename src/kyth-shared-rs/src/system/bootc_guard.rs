//! Fixed-channel bootc gateway used by the Hub and system recipes.

use std::process::Output;
use std::time::Duration;

/// Filesystem lock serializing every mutating bootc operation on the host.
/// `safe_upgrade`, the update watcher, `switch()`, and the Hub's
/// rollback/switch/finalize launches all go through [`with_bootc_lock`] so
/// two writers can never interleave `bootc upgrade` / `switch` / `rollback`.
pub const BOOTC_LOCK_PATH: &str = "/run/kyth-bootc.lock";

/// Run `op` while holding an exclusive non-blocking `flock` on
/// [`BOOTC_LOCK_PATH`]. The lock is released before returning, including on
/// `op` failure. A busy lock maps to a retryable "another upgrade" message
/// so callers can surface it without inventing their own wording.
pub fn with_bootc_lock<T>(op: impl FnOnce() -> Result<T, String>) -> Result<T, String> {
    with_bootc_lock_at(std::path::Path::new(BOOTC_LOCK_PATH), op)
}

fn with_bootc_lock_at<T>(
    path: &std::path::Path,
    op: impl FnOnce() -> Result<T, String>,
) -> Result<T, String> {
    let lock = std::fs::OpenOptions::new()
        .create(true)
        .write(true)
        .open(path)
        .map_err(|error| format!("Could not open the bootc upgrade lock: {error}"))?;
    rustix::fs::flock(&lock, rustix::fs::FlockOperation::NonBlockingLockExclusive).map_err(
        |_| "Another bootc upgrade is in progress; will retry on the next run".to_string(),
    )?;
    let result = op();
    let _ = rustix::fs::flock(&lock, rustix::fs::FlockOperation::Unlock);
    result
}

fn run(program: &str, args: &[&str], timeout: Duration) -> Result<Output, String> {
    let mut argv = vec![program.to_string()];
    argv.extend(args.iter().map(|arg| (*arg).to_string()));
    crate::system::process::run_bounded(&argv, timeout)
        .map_err(|error| format!("{program} could not run: {error}"))
}

/// Read the current deployment status. This is a pure read: unlike
/// `switch()`, it must never remount `/boot` read-write. The remount was
/// pure overhead here — status never writes to `/boot` — and under
/// `kyth-probe.service`'s syscall-filtered sandbox the `mount` binary it
/// spawned segfaulted instead of failing cleanly, coredumping on every
/// probe run.
pub fn status(json: bool) -> Result<String, String> {
    let args = if json {
        vec!["status", "--json"]
    } else {
        vec!["status"]
    };
    let output = run("/usr/bin/bootc", &args, Duration::from_secs(30))?;
    if output.status.success() {
        return Ok(String::from_utf8_lossy(&output.stdout).to_string());
    }
    if json {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_string());
    }
    let fallback = run("/usr/bin/rpm-ostree", &["status"], Duration::from_secs(30))?;
    if fallback.status.success() {
        return Ok(String::from_utf8_lossy(&fallback.stdout).to_string());
    }
    Err(String::from_utf8_lossy(&output.stderr).trim().to_string())
}

/// Check the tracked image for an update without downloading image layers or
/// changing the staged deployment. This is bootc's registry-aware path, so
/// the Hub does not need a separate skopeo client or transport configuration.
pub fn check() -> Result<String, String> {
    let output = run(
        "/usr/bin/bootc",
        &["upgrade", "--check"],
        Duration::from_secs(90),
    )?;
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    let detail = if stdout.is_empty() {
        stderr.clone()
    } else if stderr.is_empty() {
        stdout
    } else {
        format!("{stdout}\n{stderr}")
    };
    if output.status.success() {
        Ok(detail)
    } else if detail.is_empty() {
        Err(format!(
            "bootc update check failed (exit code {}).",
            output.status.code().unwrap_or(-1)
        ))
    } else {
        Err(detail)
    }
}

pub fn switch(channel: &str) -> Result<String, String> {
    let reference = match channel {
        "latest" => "ghcr.io/kyth-os/kyth:latest",
        "testing" => "ghcr.io/kyth-os/kyth:testing",
        "latest-cachy" => "ghcr.io/kyth-os/kyth:latest-cachy",
        "testing-cachy" => "ghcr.io/kyth-os/kyth:testing-cachy",
        _ => return Err("unsupported bootc channel".to_string()),
    };
    crate::system::boot_finalize::prepare_boot()?;
    with_bootc_lock(|| {
        let output = run(
            "/usr/bin/bootc",
            &["switch", reference],
            Duration::from_secs(3600),
        )?;
        let detail = format!(
            "{}{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
        if !output.status.success() {
            return Err(detail.trim().to_string());
        }
        crate::system::boot_finalize::finalize_staged(false)?;
        Ok(detail.trim().to_string())
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lock_serializes_and_reports_busy() {
        // Exercise the helper against a tempdir lock: the real
        // /run/kyth-bootc.lock is only writable as root.
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("kyth-bootc.lock");
        // Success + failure both release: a second acquisition must succeed.
        assert!(with_bootc_lock_at(&path, || Ok::<&str, String>("ok")).unwrap() == "ok");
        assert!(with_bootc_lock_at(&path, || Err::<&str, String>("boom".into())).is_err());
        assert!(with_bootc_lock_at(&path, || Ok::<(), String>(())).is_ok());
        // A held lock maps to the retryable busy message.
        let held = std::fs::OpenOptions::new()
            .create(true)
            .write(true)
            .open(&path)
            .expect("lock file opens");
        rustix::fs::flock(&held, rustix::fs::FlockOperation::NonBlockingLockExclusive)
            .expect("test holds the lock");
        let error = with_bootc_lock_at(&path, || Ok::<(), String>(())).unwrap_err();
        assert!(
            error.contains("Another bootc upgrade is in progress"),
            "unexpected: {error}"
        );
        let _ = rustix::fs::flock(&held, rustix::fs::FlockOperation::Unlock);
        assert!(with_bootc_lock_at(&path, || Ok::<(), String>(())).is_ok());
    }
}
