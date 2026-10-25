//! Port of `kyth_shared.system.firmware` — fwupd helpers.

use super::runtime_output::count_fwupd_updates;
use rustix::fs::{flock, FlockOperation};
use std::fs::OpenOptions;
use std::time::Duration;

fn run_with_timeout(cmd: &[String], timeout: Duration) -> Option<(i32, String)> {
    let (code, stdout, stderr) = run_with_timeout_split(cmd, timeout)?;
    let combined = format!("{stdout}{stderr}");
    Some((code, combined.trim().to_string()))
}

/// Like [`run_with_timeout`] but keeps stdout and stderr separate: parsers
/// (the get-updates count) must never see stderr chatter in their input,
/// while display paths still want the combined text — they use
/// [`run_with_timeout`].
fn run_with_timeout_split(cmd: &[String], timeout: Duration) -> Option<(i32, String, String)> {
    if cmd.is_empty() {
        return None;
    }
    let output = super::process::run_bounded(cmd, timeout).ok()?;
    Some((
        output.status.code().unwrap_or(-1),
        String::from_utf8_lossy(&output.stdout).trim().to_string(),
        String::from_utf8_lossy(&output.stderr).trim().to_string(),
    ))
}

pub fn firmware_refresh_commands() -> Vec<Vec<String>> {
    vec![vec![
        "fwupdmgr".to_string(),
        "refresh".to_string(),
        "--force".to_string(),
    ]]
}
pub fn firmware_devices_command() -> Vec<String> {
    vec!["fwupdmgr".to_string(), "get-devices".to_string()]
}
pub fn firmware_updates_command() -> Vec<String> {
    vec!["fwupdmgr".to_string(), "get-updates".to_string()]
}
pub fn firmware_update_command() -> Vec<String> {
    vec![
        "fwupdmgr".to_string(),
        "update".to_string(),
        "--assume-yes".to_string(),
        "--no-reboot-check".to_string(),
    ]
}

pub fn run_firmware_refresh(timeout: u64) -> (bool, String) {
    let cmd = firmware_refresh_commands()[0].clone();
    match run_with_timeout(&cmd, Duration::from_secs(timeout)) {
        Some((0, out)) => (true, out),
        Some((_, out)) if !out.is_empty() => (false, out),
        Some((_, _)) => (false, "".to_string()),
        None => (
            false,
            format!("fwupdmgr refresh timed out after {}s", timeout),
        ),
    }
}

/// Count pending firmware updates, or `None` when the count could not be
/// determined (fwupdmgr missing, timed out, or exited with an error).
/// Callers must not render `None` as "no updates": fwupd's genuine
/// no-updates outcome (exit 2, or exit 0 with no device blocks) is
/// `Some(0)`. Only stdout is parsed — stderr chatter (warnings, progress)
/// can contain "Device ID:"-shaped text and must not inflate the count.
pub fn check_firmware_updates(timeout: u64) -> Option<u32> {
    let cmd = firmware_updates_command();
    let result = run_with_timeout_split(&cmd, Duration::from_secs(timeout))
        .map(|(code, stdout, _)| (code, stdout));
    classify_get_updates(result)
}

/// Pure classification of a `fwupdmgr get-updates` outcome into the
/// [`check_firmware_updates`] contract, so the mapping is unit-testable
/// without a live fwupd.
fn classify_get_updates(result: Option<(i32, String)>) -> Option<u32> {
    match result {
        Some((2, _)) => Some(0),
        Some((0, stdout)) if stdout.trim().is_empty() => Some(0),
        Some((0, stdout)) => Some(count_fwupd_updates(&stdout) as u32),
        _ => None,
    }
}

pub fn run_firmware_update(timeout: u64) -> (bool, String) {
    let cmd = firmware_update_command();
    match run_with_timeout(&cmd, Duration::from_secs(timeout)) {
        Some((0, out)) => (true, out),
        Some((_, out)) => (false, out),
        None => (
            false,
            format!("fwupdmgr update timed out after {}s", timeout),
        ),
    }
}

/// Run the interactive `ujust firmware-update` flow through the same bounded
/// fwupd command definitions used by the update watcher.  The watcher owns
/// the cross-process lock; this user-triggered route owns no long-lived state
/// and therefore reports each failure directly to its caller.
pub fn firmware_update_recipe() -> Result<String, String> {
    let (refreshed, refresh_output) = run_firmware_refresh(60);
    if !refreshed {
        return Err(if refresh_output.is_empty() {
            "fwupdmgr refresh failed".to_string()
        } else {
            refresh_output
        });
    }
    let count =
        match check_firmware_updates(20) {
            Some(count) => count,
            None => return Err(
                "Could not check for firmware updates: fwupdmgr get-updates failed or timed out."
                    .to_string(),
            ),
        };
    if count == 0 {
        return Ok("No firmware updates available.".to_string());
    }
    let (updated, output) = run_firmware_update(600);
    if updated {
        Ok(output)
    } else {
        Err(if output.is_empty() {
            "fwupdmgr update failed".to_string()
        } else {
            output
        })
    }
}

/// Refresh metadata, count pending devices, and stage updates while sharing
/// the same non-blocking lock used by Guardian and the Hub firmware probe.
/// A lock miss is intentionally a no-op: another owner will finish the batch.
pub fn stage_firmware_batch() -> (bool, i32, String) {
    let path = std::env::var_os("KYTH_FWUPD_LOCK")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| "/run/kyth-fwupd.lock".into());
    let Some(parent) = path.parent() else {
        return (false, 0, String::new());
    };
    if std::fs::create_dir_all(parent).is_err() {
        return (false, 0, String::new());
    }
    let Ok(lock) = OpenOptions::new().create(true).write(true).open(path) else {
        return (false, 0, String::new());
    };
    if flock(&lock, FlockOperation::NonBlockingLockExclusive).is_err() {
        return (false, 0, String::new());
    }
    let (refreshed, refresh_output) = run_firmware_refresh(60);
    if !refreshed {
        let _ = flock(&lock, FlockOperation::Unlock);
        return (
            false,
            0,
            if refresh_output.is_empty() {
                "fwupdmgr refresh failed".to_string()
            } else {
                refresh_output
            },
        );
    }
    let count = check_firmware_updates(20);
    let count = match count {
        Some(count) if count > 0 => count as i32,
        Some(_) => {
            let _ = flock(&lock, FlockOperation::Unlock);
            return (false, 0, String::new());
        }
        None => {
            let _ = flock(&lock, FlockOperation::Unlock);
            return (
                false,
                0,
                "Could not check for firmware updates: fwupdmgr get-updates failed or timed out."
                    .to_string(),
            );
        }
    };
    let result = run_firmware_update(600);
    let _ = flock(&lock, FlockOperation::Unlock);
    (result.0, count, result.1)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn commands() {
        assert_eq!(firmware_devices_command(), vec!["fwupdmgr", "get-devices"]);
        assert_eq!(firmware_updates_command(), vec!["fwupdmgr", "get-updates"]);
    }

    #[test]
    fn fwupd_count_is_nonnegative_when_no_updates_exist() {
        assert_eq!(count_fwupd_updates("No updates available\n"), 0);
    }

    #[test]
    fn get_updates_classification_distinguishes_unknown_from_none_pending() {
        // Timeout / spawn failure: unknown, NOT zero.
        assert_eq!(classify_get_updates(None), None);
        // fwupd's dedicated "no updates" exit code.
        assert_eq!(classify_get_updates(Some((2, String::new()))), Some(0));
        // Exit 0 with empty output: genuinely nothing pending.
        assert_eq!(classify_get_updates(Some((0, "  \n".into()))), Some(0));
        assert_eq!(
            classify_get_updates(Some((0, "No updates available\n".into()))),
            Some(0)
        );
        // Exit 0 with device blocks: counted from stdout.
        let out = "Device ID: a\nDevice ID: b\n".to_string();
        assert_eq!(classify_get_updates(Some((0, out))), Some(2));
        // Any other exit (daemon down, metadata error, ...) is unknown.
        assert_eq!(classify_get_updates(Some((1, String::new()))), None);
        assert_eq!(classify_get_updates(Some((-1, String::new()))), None);
    }

    #[test]
    fn split_runner_keeps_stderr_out_of_the_parse_stream() {
        let cmd = vec![
            "sh".to_string(),
            "-c".to_string(),
            "echo 'Device ID: real'; echo 'Device ID: decoy' >&2".to_string(),
        ];
        let (code, stdout, stderr) =
            run_with_timeout_split(&cmd, Duration::from_secs(10)).expect("sh must run");
        assert_eq!(code, 0);
        // The combined runner used by display paths keeps both streams...
        let combined = run_with_timeout(&cmd, Duration::from_secs(10)).unwrap().1;
        assert!(combined.contains("decoy"));
        // ...but the count only ever sees stdout.
        assert_eq!(count_fwupd_updates(&stdout), 1);
        assert!(stderr.contains("decoy"));
        assert_eq!(classify_get_updates(Some((code, stdout))), Some(1));
    }
}
