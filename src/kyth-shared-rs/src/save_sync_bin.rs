//! Native replacement for the Python `kyth-save-sync` launcher.
//!
//! Keeps a local restic repo of Steam compat saves (native + Flatpak Steam)
//! and syncs it to the configured rclone remote when one is set and
//! authenticated. Backs up the default restic include set
//! (`save_cloud::DEFAULT_RESTIC_INCLUDES`); the full `~/.var/app` Flatpak
//! data tree is only bundled with `--include-flatpak-data`, and even then
//! prints a size warning first — shader caches can add tens of GiB.
//! Every step is best-effort with the Python timeouts. Always exits `0`.
//! `save_cloud.py` stays as the Phase 3 fixture.

use std::env;
use std::path::PathBuf;
use std::time::Duration;

use kyth_shared::system::process::run_bounded;
use kyth_shared::system::save_cloud::{
    compat_drive_cs, config_path, default_restic_includes, dir_size_bytes, load,
    should_warn_flatpak_bundle, FLATPAK_DATA_WARN_BYTES,
};

fn run(argv: &[&str], timeout_secs: u64) {
    let argv: Vec<String> = argv.iter().map(|part| (*part).to_string()).collect();
    let _ = run_bounded(&argv, Duration::from_secs(timeout_secs));
}

fn gib(bytes: u64) -> f64 {
    bytes as f64 / 1024.0 / 1024.0 / 1024.0
}

fn main() -> std::process::ExitCode {
    let include_flatpak_data = env::args().any(|arg| arg == "--include-flatpak-data");
    let home = env::var_os("HOME").map(PathBuf::from).unwrap_or_default();
    let config = load(config_path(None::<PathBuf>));
    let repo = PathBuf::from(&config.repo);
    let _ = std::fs::create_dir_all(&repo);
    if !repo.join("config").exists() {
        run(&["restic", "init", "--repo", &repo.to_string_lossy()], 10);
    }
    // Default restic includes: compat prefixes plus Kyth state dirs.
    let mut targets: Vec<String> = compat_drive_cs(&home)
        .iter()
        .map(|path| path.to_string_lossy().into_owned())
        .collect();
    for include in default_restic_includes(&home) {
        let text = include.to_string_lossy().into_owned();
        if !targets.iter().any(|existing| *existing == text) {
            targets.push(text);
        }
    }
    // Optional Flatpak app-data bundle: size-warned, explicit opt-in only.
    if include_flatpak_data {
        let flatpak_data = home.join(".var/app");
        let bytes = dir_size_bytes(&flatpak_data);
        if should_warn_flatpak_bundle(&flatpak_data) {
            eprintln!(
                "kyth-save-sync: WARNING: ~/.var/app is {:.1} GiB (>= {:.0} GiB); \
                 bundling it will make a very large snapshot. Pass --include-flatpak-data \
                 again via KYTH_SAVE_SYNC_CONFIRM_BIG=1 to proceed.",
                gib(bytes),
                gib(FLATPAK_DATA_WARN_BYTES)
            );
            if env::var_os("KYTH_SAVE_SYNC_CONFIRM_BIG").is_none() {
                eprintln!("kyth-save-sync: skipping ~/.var/app (unconfirmed large bundle)");
            } else {
                targets.push(flatpak_data.to_string_lossy().into_owned());
            }
        } else {
            eprintln!(
                "kyth-save-sync: including ~/.var/app ({:.1} GiB)",
                gib(bytes)
            );
            targets.push(flatpak_data.to_string_lossy().into_owned());
        }
    }
    if !targets.is_empty() {
        let repo_arg = repo.to_string_lossy();
        let mut argv: Vec<&str> = vec!["restic", "--repo", &repo_arg, "backup"];
        let owned: Vec<String> = targets;
        let refs: Vec<&str> = owned.iter().map(String::as_str).collect();
        argv.extend(refs);
        run(&argv, 60);
    }
    let remote = config.remote.clone();
    if !remote.is_empty() && home.join(".config/rclone/rclone.conf").exists() {
        let repo_arg = repo.to_string_lossy();
        run(&["rclone", "sync", &repo_arg, &remote], 120);
    }
    let remote = if remote.is_empty() {
        "none".to_string()
    } else {
        remote
    };
    println!("kyth-save-sync: repo {} remote {remote}", repo.display());
    std::process::ExitCode::SUCCESS
}
