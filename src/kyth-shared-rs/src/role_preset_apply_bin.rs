//! Native replacement for the Python `kyth-apply-role-preset` launcher.
//!
//! Applies a role profile in two halves: the Plasma layout half (kickoff
//! favorites, discover notifier, widget-update script, `kbuildsycoca`) and
//! the declarative-home half (missing Flatpaks, Distroboxes, and editor
//! extensions only — a second run is a no-op). Exit status is the layout
//! result (`0`, or `64` for an unknown profile); preset warnings go to
//! stderr without affecting it. Both Python sources stay as Phase 3
//! fixtures.

use std::collections::HashSet;
use std::env;
use std::path::Path;
use std::process::ExitCode;
use std::time::Duration;

use kyth_shared::system::desktop_plasma::{
    default_application_roots, evaluate_plasma_argv, filter_available_launchers, kwriteconfig_argv,
    normalize_role_arg, profile_stamp_path, qdbus_candidates, render_role_script, role_launchers,
    role_layout_target, LauncherChoice, HIDDEN_TRAY_ITEMS, TRAY_ITEMS,
};
use kyth_shared::system::process::{find_executable, run_bounded, run_bounded_success};
use kyth_shared::system::role_preset::{
    config_path as preset_config_path, defaults_for, distrobox_create_argv, extension_install_argv,
    flatpak_install_argv, parse_distrobox_list, parse_extension_list, parse_flatpak_list,
    plan_installs, save, Role, VSCODE_BINARIES, VSCODE_INSTALL_BINARIES,
};

const USAGE: &str = "Usage: kyth-apply-role-preset [everyday|gaming|dev|creator]";

fn find_binary(name: &str) -> Option<String> {
    find_executable(name).map(|path| path.to_string_lossy().into_owned())
}

fn first_binary(names: &[&str]) -> Option<String> {
    names.iter().find_map(|name| find_binary(name))
}

fn probe(argv: &[String], timeout_secs: u64) -> Option<String> {
    run_bounded(argv, Duration::from_secs(timeout_secs))
        .ok()
        .and_then(|output| {
            output
                .status
                .success()
                .then(|| String::from_utf8_lossy(&output.stdout).into_owned())
        })
}

/// Layout half, mirroring `apply_role_preset` (idempotent, always safe).
fn apply_layout(profile: &str) -> i32 {
    let Some(launchers) = role_launchers(role_layout_target(profile)) else {
        return 64;
    };
    let home = env::var_os("HOME")
        .map(std::path::PathBuf::from)
        .unwrap_or_default();
    let stamp = profile_stamp_path(&home);
    if let Some(parent) = stamp.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let _ = std::fs::write(&stamp, format!("{profile}\n"));
    let choices: Vec<LauncherChoice> = launchers
        .iter()
        .map(|name| LauncherChoice::Single((*name).to_string()))
        .collect();
    let available: Vec<String> =
        filter_available_launchers(&choices, &default_application_roots(&home));
    let csv = available.join(",");
    if let Some(kwrite) = first_binary(&["kwriteconfig6", "kwriteconfig5", "kwriteconfig"]) {
        let _ = run_bounded(
            &kwriteconfig_argv(
                &kwrite,
                "kickoffrc",
                &["Favorites"],
                "FavoriteURLs",
                &csv,
                None,
            ),
            Duration::from_secs(5),
        );
        let _ = run_bounded(
            &kwriteconfig_argv(
                &kwrite,
                "plasma-discoverrc",
                &["UpdatesNotifier"],
                "UseNotifications",
                "false",
                Some("bool"),
            ),
            Duration::from_secs(5),
        );
    }
    if let Some(qdbus) = first_binary(&qdbus_candidates()) {
        let script = render_role_script(&csv, &TRAY_ITEMS.join(","), &HIDDEN_TRAY_ITEMS.join(","));
        let _ = run_bounded(
            &evaluate_plasma_argv(&qdbus, &script),
            Duration::from_secs(15),
        );
    }
    if let Some(sycoca) = first_binary(&["kbuildsycoca6", "kbuildsycoca"]) {
        let _ = run_bounded(
            &[sycoca, "--noincremental".to_string()],
            Duration::from_secs(10),
        );
    }
    0
}

/// Preset half, mirroring `apply_preset` (install-only-missing).
fn install_extension_with<F>(extension: &str, binaries: &[&str], mut run: F) -> bool
where
    F: FnMut(&str, &str) -> bool,
{
    binaries.iter().any(|binary| run(binary, extension))
}

fn apply_preset(profile: Role) -> Vec<String> {
    let preset = defaults_for(profile);
    let mut warnings = Vec::new();
    if let Err(error) = save(preset_config_path(None::<&Path>), &preset) {
        warnings.push(format!("could not save preset: {error}"));
    }
    let have_flatpaks = probe(
        &[
            "flatpak".to_string(),
            "list".to_string(),
            "--app".to_string(),
            "--columns=application".to_string(),
        ],
        10,
    )
    .map(|text| parse_flatpak_list(&text))
    .unwrap_or_default();
    let have_boxes = probe(
        &[
            "distrobox".to_string(),
            "list".to_string(),
            "--no-color".to_string(),
        ],
        10,
    )
    .map(|text| parse_distrobox_list(&text))
    .unwrap_or_default();
    let mut have_extensions: HashSet<String> = HashSet::new();
    for binary in VSCODE_BINARIES {
        if let Some(text) = probe(&[binary.to_string(), "--list-extensions".to_string()], 10) {
            have_extensions = parse_extension_list(&text);
            break;
        }
    }
    let (installed, _skipped) =
        plan_installs(&preset, &have_flatpaks, &have_boxes, &have_extensions);
    for app in &preset.flatpaks {
        if installed.contains(app) {
            if !run_bounded_success(&flatpak_install_argv(app), Duration::from_secs(300)) {
                warnings.push(format!("Flatpak install failed: {app}"));
            }
        }
    }
    for name in &preset.distroboxes {
        if installed.contains(name) {
            if !run_bounded_success(&distrobox_create_argv(name), Duration::from_secs(300)) {
                warnings.push(format!("Distrobox creation failed: {name}"));
            }
        }
    }
    for extension in &preset.vscode_extensions {
        if installed.contains(extension) {
            let succeeded =
                install_extension_with(extension, &VSCODE_INSTALL_BINARIES, |binary, extension| {
                    let Some(path) = find_binary(binary) else {
                        return false;
                    };
                    run_bounded_success(
                        &extension_install_argv(&path, extension),
                        Duration::from_secs(60),
                    )
                });
            if !succeeded {
                warnings.push(format!("VS Code extension install failed: {extension}"));
            }
        }
    }
    warnings
}

fn main() -> ExitCode {
    let arg = env::args().nth(1).unwrap_or_else(|| "everyday".to_string());
    let Some(profile) = normalize_role_arg(&arg) else {
        eprintln!("{USAGE}");
        return ExitCode::from(64);
    };
    let layout_rc = apply_layout(profile);
    for warning in apply_preset(Role::parse(Some(profile))) {
        eprintln!("preset apply warning: {warning}");
    }
    ExitCode::from(layout_rc as u8)
}

#[cfg(test)]
mod tests {
    use super::install_extension_with;

    #[test]
    fn extension_install_falls_back_after_nonzero_exit() {
        let mut attempted = Vec::new();
        let succeeded =
            install_extension_with("publisher.extension", &["code", "codium"], |binary, _| {
                attempted.push(binary.to_string());
                binary == "codium"
            });
        assert!(succeeded);
        assert_eq!(attempted, ["code", "codium"]);
    }

    #[test]
    fn extension_install_reports_failure_when_all_candidates_fail() {
        let mut attempted = 0;
        let succeeded =
            install_extension_with("publisher.extension", &["code", "codium"], |_, _| {
                attempted += 1;
                false
            });
        assert!(!succeeded);
        assert_eq!(attempted, 2);
    }
}
