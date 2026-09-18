//! Policy data for the `default-flatpaks` first-boot install owned by
//! `kyth-runtime` (`runtime_bin.rs`).
//!
//! The app list, install flags, versioned sentinel, and dedicated timeout
//! live here so the binary stays a thin dispatcher and the policy is unit
//! tested. The sentinel filename is VERSIONED: bump `SENTINEL_VERSION` any
//! time the app list changes, because the old sentinel survives OS upgrades
//! in /var (which bootc never touches) and existing users would otherwise
//! never see new apps. Keep the filename in sync with
//! `build_files/kyth-default-flatpaks.service` (`ConditionPathExists`).

use std::time::Duration;

/// Bump with the app list; the filename below derives from this.
pub const SENTINEL_VERSION: u32 = 14;
/// First-boot pull of several large runtimes/apps; must not share the
/// generic 120 s command bound (`COMMAND_TIMEOUT` in `runtime_bin.rs`).
/// The unit allows 3600 s; 1800 s leaves headroom for retries on next boot.
pub const INSTALL_TIMEOUT: Duration = Duration::from_secs(1800);
/// Install for all users, consistent with `kyth-flathub-setup.service`.
pub const REMOTE: &str = "flathub";

/// First boot installs Steam only: a six-app pull on metered/slow first
/// boot delayed login-ready by gigabytes. Everything else stays one click
/// away in the System Hub (see `ON_DEMAND_APPS` + `hub_install_args`).
pub const APPS: &[&str] = &["com.valvesoftware.Steam"];

/// Former first-boot apps, now on-demand Hub installs: same flags, installed
/// only when the user picks them in Hub > Apps.
pub const ON_DEMAND_APPS: &[&str] = &[
    "net.lutris.Lutris",
    "com.heroicgameslauncher.hgl",
    "org.videolan.VLC",
    "com.brave.Browser",
    "org.libreoffice.LibreOffice",
];

/// Args after the `flatpak` program for one on-demand Hub install of `app`.
/// Rejects anything outside [`ON_DEMAND_APPS`] + [`APPS`] so the Hub cannot
/// be driven to install an arbitrary ref.
pub fn hub_install_args(app: &str) -> Option<Vec<String>> {
    if !APPS.contains(&app) && !ON_DEMAND_APPS.contains(&app) {
        return None;
    }
    Some(
        ["install", "--system", "--or-update", "-y", REMOTE, app]
            .iter()
            .map(|part| (*part).to_string())
            .collect(),
    )
}

/// Versioned stamp written only on full success; a flaky first-online pull
/// leaves it unset so the next boot retries.
pub fn sentinel_path() -> String {
    format!("/var/lib/kyth/default-flatpaks-v{SENTINEL_VERSION}-done")
}

/// Args after the `flatpak` program: system-wide, idempotent
/// (`--or-update` installs or updates), non-interactive.
pub fn install_args() -> Vec<String> {
    std::iter::empty()
        .chain(["install", "--system", "--or-update", "-y", REMOTE])
        .chain(APPS.iter().copied())
        .map(str::to_string)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn install_is_system_wide_and_idempotent() {
        let args = install_args();
        assert!(args.contains(&"--system".to_string()));
        assert!(args.contains(&"--or-update".to_string()));
        assert!(args.contains(&"-y".to_string()));
        assert!(args.contains(&REMOTE.to_string()));
        for app in APPS {
            assert!(args.contains(&app.to_string()), "{app} missing");
        }
    }

    #[test]
    fn sentinel_is_versioned_and_matches_the_unit() {
        let path = sentinel_path();
        assert!(
            path.contains(&format!("v{SENTINEL_VERSION}-done")),
            "sentinel must embed the version: {path}"
        );
        // Pinned to what `kyth-default-flatpaks.service` conditions on;
        // bump both together with the app list.
        assert_eq!(path, "/var/lib/kyth/default-flatpaks-v14-done");
    }

    #[test]
    fn first_boot_is_steam_only_and_rest_is_on_demand() {
        assert_eq!(APPS, &["com.valvesoftware.Steam"]);
        for app in ON_DEMAND_APPS {
            let args = hub_install_args(app).expect("{app} must be installable on demand");
            assert!(args.contains(&"--system".to_string()));
            assert!(args.contains(&"--or-update".to_string()));
            assert!(args.contains(&app.to_string()));
        }
        assert!(hub_install_args("org.evil.App").is_none());
        assert!(hub_install_args("com.valvesoftware.Steam").is_some());
    }

    #[test]
    fn install_has_its_own_long_timeout() {
        assert!(INSTALL_TIMEOUT > Duration::from_secs(120));
    }
}
