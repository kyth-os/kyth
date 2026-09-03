//! Rust-owned execution handoff for destructive installer image writes.
//!
//! The compatibility Python service still owns phase orchestration and
//! recovery.  It invokes this helper only with a typed bootc operation on
//! stdin.  The helper validates and projects the request with the same Rust
//! plan used by the native clients, then replaces itself with bootc so the
//! caller's cancellation and timeout signals still target the real command.

mod installer_bootc;
#[allow(dead_code)]
mod installer_plan;

use std::io::{self, Read};
use std::os::unix::process::CommandExt;
use std::process::{Command, ExitCode};

use installer_bootc::BootcInstallInput;

const MAX_OPERATION_BYTES: usize = 64 * 1024;

fn read_operation() -> Result<BootcInstallInput, String> {
    let mut input = Vec::new();
    io::stdin()
        .take((MAX_OPERATION_BYTES + 1) as u64)
        .read_to_end(&mut input)
        .map_err(|error| format!("could not read installer operation: {error}"))?;
    decode_operation(&input)
}

fn decode_operation(input: &[u8]) -> Result<BootcInstallInput, String> {
    if input.len() > MAX_OPERATION_BYTES {
        return Err("installer operation is too large".to_string());
    }
    serde_json::from_slice(input)
        .map_err(|error| format!("invalid installer operation JSON: {error}"))
}

fn operation_args_valid(args: &[String]) -> bool {
    args == [
        "--operation".to_string(),
        "bootc-install".to_string(),
    ]
}

fn run(args: &[String]) -> Result<ExitCode, String> {
    if unsafe { libc::geteuid() } != 0 {
        return Err("kyth-installer-exec must run as root".to_string());
    }
    if !operation_args_valid(args) {
        return Err("only the bootc-install operation is supported".to_string());
    }

    let input = read_operation()?;
    let plan = installer_bootc::build_plan(input)?;
    // Do not resolve a root command through an inherited PATH. The plan still
    // exposes the logical `bootc` argv for parity, while the executor pins the
    // installed binary location.
    let mut command = Command::new("/usr/bin/bootc");
    command.args(&plan.argv[1..]);
    // exec(2) is deliberate: the Python streaming caller continues to own
    // the same PID, so terminate/kill cancellation cannot orphan bootc.
    let error = command.exec();
    Err(format!("could not execute bootc install: {error}"))
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
        assert!(!operation_args_valid(&["--operation".into(), "other".into()]));
        assert!(!operation_args_valid(&["--operation".into()]));
        assert!(operation_args_valid(&["--operation".into(), "bootc-install".into()]));
    }

    #[test]
    fn operation_input_is_bounded() {
        assert!(decode_operation(&vec![b' '; MAX_OPERATION_BYTES + 1]).is_err());
        assert!(decode_operation(b"not-json").is_err());
        assert!(decode_operation(
            br#"{"subcommand":"to-disk","source_imgref":"oci:/image","target_imgref":"kyth:latest","target":"/dev/sda","wipe":true}"#,
        ).is_ok());
    }
}
