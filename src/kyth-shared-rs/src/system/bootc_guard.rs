//! Fixed-channel bootc gateway used by the Hub and system recipes.

use std::process::Output;
use std::time::Duration;

fn run(program: &str, args: &[&str], timeout: Duration) -> Result<Output, String> {
    let mut argv = vec![program.to_string()];
    argv.extend(args.iter().map(|arg| (*arg).to_string()));
    crate::system::process::run_bounded(&argv, timeout)
        .map_err(|error| format!("{program} could not run: {error}"))
}

pub fn status(json: bool) -> Result<String, String> {
    crate::system::boot_finalize::prepare_boot()?;
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
}
