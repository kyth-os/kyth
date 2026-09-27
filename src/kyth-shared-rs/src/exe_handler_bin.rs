//! Native MIME-handler launcher for Windows installers and RPM packages.
//!
//! The user interface lives in the existing Kyth Tauri/React Hub. This
//! narrow executable exists so the desktop-file entry point remains native
//! while Dolphin and other XDG callers can pass a file path directly.
//!
//! Trust-once fast path: a file whose full SHA-256 the user trusted (via
//! the Hub dialog's "always run directly") launches straight into its
//! recorded runner with no UI. Anything else forwards to the Hub dialog.

use std::env;
use std::path::PathBuf;
use std::process::{Command, ExitCode};

use kyth_shared::system::{exe_trust, windows_installer};

const HUB_SHELL: &str = "/usr/bin/kyth-hub-shell";

fn handler_path(args: impl IntoIterator<Item = String>) -> Option<String> {
    let mut path = None;
    for arg in args.into_iter().skip(1) {
        // Retain the legacy flag as a harmless compatibility spelling. The
        // Hub always presents a dialog, so no separate mode is needed.
        if arg != "--dialog" && path.is_none() {
            path = Some(arg);
        }
    }
    path
}

fn home_dir() -> PathBuf {
    env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/"))
}

/// Canonicalize and refuse symlinks/non-files, mirroring the Hub's
/// `regular_handler_path`: a trusted hash must name the real file.
fn regular_path(raw: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(raw);
    let metadata =
        std::fs::symlink_metadata(&path).map_err(|error| format!("could not be read: {error}"))?;
    if metadata.file_type().is_symlink() || !metadata.file_type().is_file() {
        return Err("not a regular file".to_string());
    }
    path.canonicalize()
        .map_err(|error| format!("could not be read: {error}"))
}

/// Trusted fast path: exact-content match launches with no dialog.
/// Returns None when the file is not trusted (caller forwards to Hub).
fn try_trusted_launch(path: &std::path::Path) -> Option<ExitCode> {
    let digest = exe_trust::full_sha256(path)?;
    let runner = exe_trust::trusted_runner(&home_dir(), &digest)?;
    match runner.as_str() {
        exe_trust::RUNNER_BOTTLES => {
            let request = windows_installer::inspect_installer(path).ok()?;
            match windows_installer::launch_in_bottles(&request, home_dir()) {
                Ok(_) => Some(ExitCode::SUCCESS),
                Err(error) => {
                    eprintln!(
                        "kyth-exe-handler: trusted Bottles launch failed: {}",
                        error.message
                    );
                    Some(ExitCode::from(1))
                }
            }
        }
        exe_trust::RUNNER_UMU => match windows_installer::launch_in_umu(path) {
            Ok(_) => Some(ExitCode::SUCCESS),
            Err(error) => {
                eprintln!("kyth-exe-handler: trusted umu launch failed: {error}");
                Some(ExitCode::from(1))
            }
        },
        _ => None,
    }
}

fn forward_to_hub(path: &str) -> ExitCode {
    match Command::new(HUB_SHELL)
        .arg("--exe-handler")
        .arg(path)
        .status()
    {
        Ok(status) if status.success() => ExitCode::SUCCESS,
        Ok(status) => ExitCode::from(status.code().unwrap_or(1).clamp(1, 255) as u8),
        Err(error) => {
            eprintln!("kyth-exe-handler: could not start Kyth Hub: {error}");
            ExitCode::from(1)
        }
    }
}

fn main() -> ExitCode {
    let Some(raw) = handler_path(env::args()) else {
        // No file: almost certainly a broken desktop-file association, not
        // a successful no-op. Say so instead of exiting 0.
        eprintln!("kyth-exe-handler: no file path given; check the .desktop Exec line");
        return ExitCode::from(1);
    };
    let path = match regular_path(&raw) {
        Ok(path) => path,
        Err(error) => {
            eprintln!("kyth-exe-handler: {raw}: {error}");
            return forward_to_hub(&raw);
        }
    };
    if let Some(code) = try_trusted_launch(&path) {
        return code;
    }
    forward_to_hub(&raw)
}

#[cfg(test)]
mod tests {
    use super::handler_path;

    #[test]
    fn accepts_legacy_dialog_flag_without_treating_it_as_a_path() {
        assert_eq!(
            handler_path(["kyth-exe-handler", "--dialog", "/tmp/setup.exe"].map(String::from)),
            Some("/tmp/setup.exe".into())
        );
    }

    #[test]
    fn missing_path_is_an_error_not_a_silent_success() {
        // handler_path returns None with no file; main() maps that to
        // exit 1 (broken association), never a silent 0.
        assert_eq!(handler_path(["kyth-exe-handler"].map(String::from)), None);
    }

    #[test]
    fn untrusted_files_fall_through_to_the_hub() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("setup.exe");
        std::fs::write(&path, "demo").unwrap();
        assert!(super::try_trusted_launch(&path).is_none());
    }

    #[test]
    fn regular_path_refuses_symlinks() {
        let directory = tempfile::tempdir().unwrap();
        let target = directory.path().join("real.exe");
        std::fs::write(&target, "demo").unwrap();
        let link = directory.path().join("link.exe");
        std::os::unix::fs::symlink(&target, &link).unwrap();
        assert!(super::regular_path(link.to_str().unwrap()).is_err());
        assert!(super::regular_path(target.to_str().unwrap()).is_ok());
    }
}
