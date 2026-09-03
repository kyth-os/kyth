//! Rust-owned execution handoff for destructive installer image writes.
//!
//! The compatibility Python service still owns phase orchestration and
//! recovery.  It invokes this helper only with a typed bootc operation on
//! stdin. The helper validates and projects the request with the same Rust
//! plans used by the native clients, then replaces itself with the selected
//! utility so the
//! caller's cancellation and timeout signals still target the real command.

mod installer_bootc;
mod installer_disk;
#[allow(dead_code)]
mod installer_plan;

use std::io::{self, Read, Write};
use std::os::unix::process::CommandExt;
use std::process::{Command, ExitCode, Stdio};

const MAX_OPERATION_BYTES: usize = 64 * 1024;

fn read_operation_bytes() -> Result<Vec<u8>, String> {
    let mut input = Vec::new();
    io::stdin()
        .take((MAX_OPERATION_BYTES + 1) as u64)
        .read_to_end(&mut input)
        .map_err(|error| format!("could not read installer operation: {error}"))?;
    decode_operation_bytes(&input)
}

fn decode_operation_bytes(input: &[u8]) -> Result<Vec<u8>, String> {
    if input.len() > MAX_OPERATION_BYTES {
        return Err("installer operation is too large".to_string());
    }
    serde_json::from_slice::<serde_json::Value>(input)
        .map_err(|error| format!("invalid installer operation JSON: {error}"))?;
    Ok(input.to_vec())
}

fn operation_args_valid(args: &[String]) -> bool {
    args.len() == 2
        && args[0] == "--operation"
        && matches!(args[1].as_str(), "bootc-install" | "disk")
}

fn run(args: &[String]) -> Result<ExitCode, String> {
    if unsafe { libc::geteuid() } != 0 {
        return Err("kyth-installer-exec must run as root".to_string());
    }
    if !operation_args_valid(args) {
        return Err("unsupported installer operation".to_string());
    }

    let input = read_operation_bytes()?;
    let (argv, needs_confirmation, operation) = match args[1].as_str() {
        "bootc-install" => {
            let input = serde_json::from_slice::<installer_bootc::BootcInstallInput>(&input)
                .map_err(|error| format!("invalid bootc install operation JSON: {error}"))?;
            let plan = installer_bootc::build_plan(input)?;
            (plan.argv, false, "bootc install")
        }
        "disk" => {
            let input = serde_json::from_slice::<installer_disk::DiskOperationInput>(&input)
                .map_err(|error| format!("invalid disk operation JSON: {error}"))?;
            let plan = installer_disk::build_plan(input)?;
            (plan.argv, plan.needs_confirmation, "disk operation")
        }
        _ => unreachable!("operation_args_valid checked the operation"),
    };
    // Do not resolve a root command through an inherited PATH. The plan still
    // exposes the logical `bootc` argv for parity, while the executor pins the
    // installed binary location.
    let executable = argv
        .first()
        .ok_or_else(|| format!("{operation} plan was empty"))?;
    // All executable paths come from the fixed Rust operation plan.
    let mut command = Command::new(executable);
    command.args(&argv[1..]);
    if needs_confirmation {
        command.stdin(Stdio::piped());
        // Ensure a helper cancellation cannot leave an interactive child
        // running after the parent process has gone away.
        let mut child = unsafe {
            command
                .pre_exec(|| {
                    if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM) != 0 {
                        return Err(io::Error::last_os_error());
                    }
                    Ok(())
                })
                .spawn()
        }
        .map_err(|error| format!("could not spawn {operation}: {error}"))?;
        if let Some(mut stdin) = child.stdin.take() {
            if let Err(error) = stdin.write_all(b"Yes\n") {
                let _ = child.kill();
                let _ = child.wait();
                return Err(format!("could not confirm {operation}: {error}"));
            }
        }
        let status = child
            .wait()
            .map_err(|error| format!("could not wait for {operation}: {error}"))?;
        return Ok(ExitCode::from(
            status
                .code()
                .and_then(|code| u8::try_from(code).ok())
                .unwrap_or(1),
        ));
    }
    // exec(2) is deliberate: the Python streaming caller continues to own
    // the same PID, so terminate/kill cancellation cannot orphan bootc.
    let error = command.exec();
    Err(format!("could not execute {operation}: {error}"))
}

fn main() -> ExitCode {
    match run(&std::env::args().skip(1).collect::<Vec<_>>()) {
        Ok(code) => code,
        Err(error) => {
            eprintln!("{error}");
            ExitCode::from(1)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_typed_bootc_operation_is_accepted() {
        assert!(!operation_args_valid(&[
            "--operation".into(),
            "other".into()
        ]));
        assert!(!operation_args_valid(&["--operation".into()]));
        assert!(operation_args_valid(&[
            "--operation".into(),
            "bootc-install".into()
        ]));
        assert!(operation_args_valid(&["--operation".into(), "disk".into()]));
    }

    #[test]
    fn operation_input_is_bounded() {
        assert!(decode_operation_bytes(&vec![b' '; MAX_OPERATION_BYTES + 1]).is_err());
        assert!(decode_operation_bytes(b"not-json").is_err());
        assert!(serde_json::from_slice::<installer_bootc::BootcInstallInput>(
            br#"{"subcommand":"to-disk","source_imgref":"oci:/image","target_imgref":"kyth:latest","target":"/dev/sda","wipe":true}"#,
        ).is_ok());
    }
}
