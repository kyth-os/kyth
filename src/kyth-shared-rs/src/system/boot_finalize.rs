//! Rust implementation of the staged-deployment boot preparation/finalizer.

use std::path::Path;
use std::process::Output;
use std::time::Duration;

fn run(program: &str, args: &[&str], timeout: Duration) -> Result<Output, String> {
    let mut argv = vec![program.to_string()];
    argv.extend(args.iter().map(|arg| (*arg).to_string()));
    crate::system::process::run_bounded(&argv, timeout)
        .map_err(|error| format!("{program} could not run: {error}"))
}

fn successful(program: &str, args: &[&str], timeout: Duration) -> bool {
    run(program, args, timeout).is_ok_and(|output| output.status.success())
}

fn bind_result(result: Result<Output, String>) -> Result<(), String> {
    match result {
        Ok(output) if output.status.success() => Ok(()),
        Ok(output) => Err(format!(
            "could not bind /boot to /sysroot/boot: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )),
        Err(error) => Err(format!("could not bind /boot to /sysroot/boot: {error}")),
    }
}

pub fn prepare_boot() -> Result<(), String> {
    let remounted = successful(
        "mount",
        &["-o", "remount,bind,rw", "/boot"],
        Duration::from_secs(15),
    ) || successful(
        "mount",
        &["-o", "remount,rw", "/boot"],
        Duration::from_secs(15),
    );
    if !remounted {
        return Err("could not remount /boot read-write".to_string());
    }
    let sysroot_boot = Path::new("/sysroot/boot");
    if sysroot_boot.is_dir()
        && !successful("findmnt", &["-n", "/sysroot/boot"], Duration::from_secs(5))
    {
        bind_result(run(
            "mount",
            &["--bind", "/boot", "/sysroot/boot"],
            Duration::from_secs(15),
        ))?;
    }
    Ok(())
}

pub fn finalize_staged(reboot: bool) -> Result<String, String> {
    if let Err(error) = prepare_boot() {
        eprintln!("kyth-finalize-staged: {error}; trying finalize anyway");
    }
    let output = run(
        "/usr/bin/ostree",
        &["admin", "finalize-staged"],
        Duration::from_secs(120),
    )?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_string());
    }
    if reboot {
        let reboot_result = run("/usr/bin/systemctl", &["reboot"], Duration::from_secs(30))?;
        if !reboot_result.status.success() {
            return Err(String::from_utf8_lossy(&reboot_result.stderr)
                .trim()
                .to_string());
        }
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::process::ExitStatusExt;

    #[test]
    fn bind_failure_is_returned_instead_of_reported_as_prepared() {
        let output = Output {
            status: std::process::ExitStatus::from_raw(1 << 8),
            stdout: Vec::new(),
            stderr: b"permission denied".to_vec(),
        };
        let error = bind_result(Ok(output)).unwrap_err();
        assert!(error.contains("could not bind /boot to /sysroot/boot"));
        assert!(error.contains("permission denied"));
    }

    #[test]
    fn bind_timeout_or_spawn_failure_is_returned() {
        let error = bind_result(Err("timed out".to_string())).unwrap_err();
        assert!(error.contains("timed out"));
    }
}
