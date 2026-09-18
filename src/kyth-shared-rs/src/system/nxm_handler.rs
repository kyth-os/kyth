//! Native port of `build_files/scripts/sysconfig/kyth-nxm-handler`.
//!
//! Handles `nxm://` Nexus Mods links from the desktop file association: if a
//! Vortex bottle exists and `bottles-cli` is available, the link is handed
//! to Vortex; otherwise the link is logged to stdout and ignored —
//! deliberately no desktop notification, so stray links never nag.
//! Exit status mirrors the script: 1 on missing argument, 0 after
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

pub fn bottles_native_available() -> bool {
    which("bottles-cli")
}

/// True when any usable Bottles runner exists: a native `bottles-cli` on
/// PATH, or the Bottles Flatpak (how KythOS ships Bottles). Flatpak
/// detection is a pure install-marker check — no shell-out — so `decide()`
/// stays side-effect free for unit tests.
pub fn bottles_cli_available(home: &Path) -> bool {
    bottles_native_available() || super::exe_compat::bottles_flatpak_installed(home)
}

/// argv to hand an nxm:// link to Vortex: the native `bottles-cli` form only
/// when a native runner is on PATH, otherwise the Flatpak form
/// (`flatpak run --command=bottles-cli com.usebottles.bottles ...`).
pub fn vortex_launch_argv(url: &str) -> Vec<String> {
    let tail = ["run", "-b", VORTEX_BOTTLE, "-e", VORTEX_EXE, "--", url];
    if bottles_native_available() {
        std::iter::once("bottles-cli".to_string())
            .chain(tail.iter().map(|arg| (*arg).to_string()))
            .collect()
    } else {
        super::windows_installer::bottles_cli(&tail)
    }
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

/// Handle one URL. Returns the process exit code: 1 for a missing argument
/// (usage), 0 once handed to Vortex or the user has been informed.
pub fn handle(url: Option<&str>, home: &Path) -> i32 {
    match decide(url, home) {
        NxmAction::Usage => {
            eprintln!("Usage: kyth-nxm-handler nxm://...");
            1
        }
        NxmAction::LaunchVortex(url) => {
            let argv: Vec<String> = vortex_launch_argv(url);
            let launched = crate::system::process::run_bounded(&argv, Duration::from_secs(120))
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
    if vortex_bottle_dir(home).is_dir() && bottles_cli_available(home) {
        NxmAction::LaunchVortex(url)
    } else {
        NxmAction::Inform(url)
    }
}

fn inform(url: &str) {
    // Deliberately stdout-only: with no mod manager installed there is
    // nothing actionable, and a desktop popup on every stray nxm:// click
    // (or automated probe) is pure nag. Journal/stdout keeps the record.
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
    fn flatpak_bottles_routes_to_launch_with_flatpak_argv() {
        // Vortex bottle + Bottles Flatpak markers but no native bottles-cli:
        // decide() must launch (not inform) and the argv must use the
        // flatpak run form.
        let home = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(vortex_bottle_dir(home.path())).unwrap();
        std::fs::create_dir_all(
            home.path()
                .join(".local/share/flatpak/app/com.usebottles.bottles"),
        )
        .unwrap();
        if bottles_native_available() {
            // Native runner present: still launches; argv form is native.
            assert_eq!(
                decide(Some("nxm://example/mods/1/files/2"), home.path()),
                NxmAction::LaunchVortex("nxm://example/mods/1/files/2")
            );
            let argv = vortex_launch_argv("nxm://example/mods/1/files/2");
            assert_eq!(argv[0], "bottles-cli");
        } else {
            assert_eq!(
                decide(Some("nxm://example/mods/1/files/2"), home.path()),
                NxmAction::LaunchVortex("nxm://example/mods/1/files/2")
            );
            let argv = vortex_launch_argv("nxm://example/mods/1/files/2");
            assert_eq!(
                &argv[..4],
                &[
                    "flatpak",
                    "run",
                    "--command=bottles-cli",
                    "com.usebottles.bottles",
                ]
            );
            assert!(argv.contains(&"Vortex.exe".to_string()));
            assert!(argv.last().unwrap().starts_with("nxm://"));
        }
    }

    #[test]
    fn bottle_dir_path_follows_home() {
        assert_eq!(
            vortex_bottle_dir(Path::new("/home/test")),
            PathBuf::from("/home/test/.local/share/bottles/bottles/Vortex")
        );
    }
}
