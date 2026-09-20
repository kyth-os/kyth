//! Native Guardian storage maintenance action.

use std::path::Path;
use std::time::Duration;

fn run(program: &str, args: &[&str], timeout: Duration) -> Result<std::process::Output, String> {
    let mut argv = vec![program.to_string()];
    argv.extend(args.iter().map(|arg| (*arg).to_string()));
    crate::system::process::run_bounded(&argv, timeout)
        .map_err(|error| format!("{program} could not run: {error}"))
}

fn pressure_low() -> bool {
    for path in ["/proc/pressure/cpu", "/sys/fs/cgroup/cpu.pressure"] {
        let Ok(text) = std::fs::read_to_string(path) else {
            continue;
        };
        if let Some(value) = text
            .split_whitespace()
            .find_map(|part| part.strip_prefix("avg10=")?.parse::<f64>().ok())
        {
            return value < 20.0;
        }
    }
    true
}

fn on_ac() -> bool {
    let Ok(entries) = std::fs::read_dir("/sys/class/power_supply") else {
        return true;
    };
    for entry in entries.flatten() {
        let name = entry.file_name();
        if !name.to_string_lossy().starts_with("BAT") {
            continue;
        }
        if std::fs::read_to_string(entry.path().join("status"))
            .is_ok_and(|status| status.trim() == "Discharging")
        {
            return false;
        }
    }
    true
}

fn gaming_active() -> bool {
    run(
        "pgrep",
        &[
            "-f",
            "kyth-game-boost|kyth-game-launch|gamemoderun|gamescope",
        ],
        Duration::from_secs(3),
    )
    .is_ok_and(|output| output.status.success())
}

fn scrub_active() -> bool {
    ["/", "/var", "/home"].iter().any(|mount| {
        run(
            "btrfs",
            &["scrub", "status", mount],
            Duration::from_secs(10),
        )
        .is_ok_and(|output| String::from_utf8_lossy(&output.stdout).contains("running"))
    })
}

/// Post-maintenance verification for the Guardian recipe: every present
/// btrfs mount must show a finished, error-free scrub. A skipped run
/// ("already running", battery, gaming) or a scrub that errored fails
/// instead of reporting verified on an unconditional `true`.
pub fn maint_verified() -> bool {
    let mut checked = false;
    for mount in ["/", "/home", "/var"] {
        if !Path::new(mount).exists() {
            continue;
        }
        let Ok(output) = run(
            "btrfs",
            &["scrub", "status", mount],
            Duration::from_secs(10),
        ) else {
            return false;
        };
        if !output.status.success() {
            return false;
        }
        checked = true;
        if !scrub_status_clean(&String::from_utf8_lossy(&output.stdout)) {
            return false;
        }
    }
    checked
}

/// Pure parse of `btrfs scrub status` output: finished AND error-free.
/// "running" (someone else's scrub), "aborted", or any error summary
/// fails — the maintenance this verifies did not complete cleanly.
pub fn scrub_status_clean(output: &str) -> bool {
    let lower = output.to_lowercase();
    lower.contains("finished") && lower.contains("no errors") && !lower.contains("running")
}

pub fn run_maintenance() -> Result<String, String> {
    if !pressure_low() {
        return Ok("Storage maintenance skipped: CPU pressure is high.".into());
    }
    if !on_ac() {
        return Ok("Storage maintenance skipped: system is on battery.".into());
    }
    if gaming_active() {
        return Ok("Storage maintenance skipped: a game is active.".into());
    }
    if scrub_active() {
        return Ok("Storage maintenance skipped: a scrub is already running.".into());
    }

    let mut failures = Vec::new();
    for mount in ["/", "/home", "/var"] {
        if Path::new(mount).exists()
            && !run(
                "btrfs",
                &["scrub", "start", "-B", mount],
                Duration::from_secs(3600),
            )
            .is_ok_and(|output| output.status.success())
        {
            failures.push(format!("scrub {mount}"));
        }
    }
    if !run(
        "btrfs",
        &["balance", "start", "-dusage=50", "-musage=50", "/"],
        Duration::from_secs(1800),
    )
    .is_ok_and(|output| output.status.success())
    {
        failures.push("balance /".into());
    }
    if failures.is_empty() {
        Ok("Storage maintenance complete.".into())
    } else {
        Ok(format!(
            "Storage maintenance completed with skipped operations: {}.",
            failures.join(", ")
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scrub_status_requires_finished_and_error_free() {
        let clean = "scrub status for /:\n\tStatus: finished\n\tError summary: no errors found\n";
        assert!(scrub_status_clean(clean));
        assert!(!scrub_status_clean("Status: running\n"));
        assert!(!scrub_status_clean(
            "Status: finished\nError summary: 3 errors found\n"
        ));
        assert!(!scrub_status_clean(
            "Status: aborted\nError summary: no errors found\n"
        ));
        assert!(!scrub_status_clean(""));
    }
}
