//! Native port of `build_files/scripts/sysconfig/kyth-nxm-handler`.
//!
//! Handles `nxm://` Nexus Mods links from the desktop file association: if a
//! Vortex bottle exists and `bottles-cli` is available, the link is handed
//! to Vortex; otherwise the user gets a notification explaining how to set
//! that up. Exit status mirrors the script: 1 on missing argument, 0 after
//! handling or informing.

use std::path::{Path, PathBuf};
use std::time::Duration;

pub const VORTEX_BOTTLE: &str = "Vortex";
pub const VORTEX_EXE: &str = "Vortex.exe";

pub fn home_dir() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/root"))
}

pub fn vortex_bottle_dir(home: &Path) -> PathBuf {
    home.join(".local/share/bottles/bottles")
        .join(VORTEX_BOTTLE)
}

pub fn bottles_cli_available() -> bool {
    which("bottles-cli")
}

pub fn notify_available() -> bool {
    which("notify-send")
}

fn which(program: &str) -> bool {
    std::env::var_os("PATH")
        .map(|paths| {
            std::env::split_paths(&paths).any(|dir| {
                dir.join(program).is_file() || dir.join(format!("{program}.exe")).is_file()
            })
        })
        .unwrap_or(false)
}

pub fn notify_link(url: &str) {
    let _ = crate::system::process::run_bounded(
        &[
            "notify-send".to_string(),
            "NXM Link".to_string(),
            format!(
                "Install Vortex in Bottles to handle Nexus Mods download links automatically.\nLink: {url}"
            ),
            "--icon=application-x-addon".to_string(),
        ],
        Duration::from_secs(10),
    );
}

/// Handle one URL. Returns the process exit code: 1 for a missing argument
/// (usage), 0 once handed to Vortex or the user has been informed.
pub fn handle(url: Option<&str>, home: &Path) -> i32 {
    match decide(url, home) {
        NxmAction::Usage => {
            eprintln!("Usage: kyth-nxm-handler nxm://...");
            1
        }
        NxmAction::LaunchVortex(url) => {
            let launched = crate::system::process::run_bounded(
                &[
                    "bottles-cli".to_string(),
                    "run".to_string(),
                    "-b".to_string(),
                    VORTEX_BOTTLE.to_string(),
                    "-e".to_string(),
                    VORTEX_EXE.to_string(),
                    "--".to_string(),
                    url.to_string(),
                ],
                Duration::from_secs(120),
            )
            .map(|output| output.status.success())
            .unwrap_or(false);
            if launched {
                return 0;
            }
            inform(url);
            0
        }
        NxmAction::Inform(url) => {
            inform(url);
            0
        }
    }
}

/// What handling one URL requires. Pure decision, no side effects: unit
/// tests assert on this so `cargo test` on a live desktop never fires a
/// real notification (or a real bottles-cli launch).
#[derive(Debug, PartialEq, Eq)]
pub enum NxmAction<'a> {
    Usage,
    LaunchVortex(&'a str),
    Inform(&'a str),
}

pub fn decide<'a>(url: Option<&'a str>, home: &Path) -> NxmAction<'a> {
    let Some(url) = url.filter(|url| !url.is_empty()) else {
        return NxmAction::Usage;
    };
    if vortex_bottle_dir(home).is_dir() && bottles_cli_available() {
        NxmAction::LaunchVortex(url)
    } else {
        NxmAction::Inform(url)
    }
}

fn inform(url: &str) {
    if notify_available() {
        notify_link(url);
    }
    println!("NXM link received: {url}");
    println!("Install Vortex via Bottles to enable automatic mod downloads.");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_url_is_usage_error() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(decide(None, dir.path()), NxmAction::Usage);
        assert_eq!(decide(Some(""), dir.path()), NxmAction::Usage);
    }

    #[test]
    fn without_vortex_bottle_decides_inform() {
        // No bottle dir: must route to inform, never attempt bottles-cli.
        // Asserts on decide(), not handle(), so the test performs no
        // desktop side effects (no notify-send popup, no launch).
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(
            decide(Some("nxm://example/mods/1/files/2"), dir.path()),
            NxmAction::Inform("nxm://example/mods/1/files/2")
        );
    }

    #[test]
    fn bottle_dir_path_follows_home() {
        assert_eq!(
            vortex_bottle_dir(Path::new("/home/test")),
            PathBuf::from("/home/test/.local/share/bottles/bottles/Vortex")
        );
    }
}
