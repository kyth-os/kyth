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
    // A successful Kyth update already finalizes after the bootc lock is
    // released. Raw bootc staging is finalized by ostree-finalize-staged's
    // shutdown hook. Re-finalizing here can fail on an already-finalized
    // deployment and suppress the reboot, so let systemd run that hook during
    // shutdown and queue the reboot without waiting for the Hub process.
    if reboot {
        return request_reboot();
    }
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
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn request_reboot() -> Result<String, String> {
    request_reboot_with(run)
}

fn request_reboot_with<F>(mut run_command: F) -> Result<String, String>
where
    F: FnMut(&str, &[&str], Duration) -> Result<Output, String>,
{
    let output = run_command(
        "/usr/bin/systemctl",
        &["--no-block", "reboot"],
        Duration::from_secs(30),
    )?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_string());
    }
    let detail = String::from_utf8_lossy(&output.stdout).trim().to_string();
    Ok(if detail.is_empty() {
        "Restart requested.".to_string()
    } else {
        detail
    })
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

    #[test]
    fn reboot_request_is_nonblocking_and_uses_systemd() {
        let mut calls = Vec::new();
        let output = Some(Output {
            status: std::process::ExitStatus::from_raw(0),
            stdout: Vec::new(),
            stderr: Vec::new(),
        });
        let mut output = output;
        let detail = request_reboot_with(|program, args, timeout| {
            calls.push((
                program.to_string(),
                args.iter()
                    .map(|arg| (*arg).to_string())
                    .collect::<Vec<_>>(),
                timeout,
            ));
            Ok(output.take().expect("only one reboot command is expected"))
        })
        .expect("systemd should accept the reboot request");
        assert_eq!(detail, "Restart requested.");
        assert_eq!(
            calls,
            vec![(
                "/usr/bin/systemctl".to_string(),
                vec!["--no-block".to_string(), "reboot".to_string()],
                Duration::from_secs(30),
            )]
        );
    }
}
