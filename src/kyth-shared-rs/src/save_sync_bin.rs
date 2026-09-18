//! Native replacement for the Python `kyth-save-sync` launcher.
//!
//! Keeps a local restic repo of Steam compat saves (native + Flatpak Steam)
//! and syncs it to the configured rclone remote when one is set and
//! authenticated. Backs up the default restic include set
//! (`save_cloud::DEFAULT_RESTIC_INCLUDES`); the full `~/.var/app` Flatpak
//! data tree is only bundled with `--include-flatpak-data`, and even then
//! prints a size warning first — shader caches can add tens of GiB.
//!
//! Safety rules, all fail-closed:
//! * Every step reports its status and any failure yields a nonzero exit —
//!   the timer's only signal is the exit code, so swallowing a failure
//!   would fake a healthy save backup.
//! * A configured-but-missing `password_file` refuses to run: backing up
//!   into (or `init`-ing over) a repo we cannot unlock destroys restores.
//! * A repo on external media (`/run/media/…`, `/mnt/…`) is only touched
//!   when that media is actually mounted — otherwise the backup would land
//!   in an unmounted stub dir on the root filesystem.
//! * `rclone sync` mirrors deletions, so it is skipped when the backup
//!   failed or the repo holds no snapshots.
//! `save_cloud.py` stays as the Phase 3 fixture.

use std::env;
use std::path::{Path, PathBuf};
use std::time::Duration;

use kyth_shared::system::backup_config::repo_has_snapshots;
use kyth_shared::system::process::run_bounded;
use kyth_shared::system::save_cloud::{
    compat_drive_cs, config_path, default_restic_includes, dir_size_bytes, load, repo_mount_ready,
    restic_prefix, should_warn_flatpak_bundle, FLATPAK_DATA_WARN_BYTES,
};

/// Run `argv` with a timeout, returning true on exit 0. Every failure is
/// reported loudly: the process exit code is the save backup's only signal
/// to the timer, so swallowing a failure would fake a healthy backup.
fn run(argv: &[String], timeout_secs: u64, label: &str) -> bool {
    match run_bounded(argv, Duration::from_secs(timeout_secs)) {
        Ok(output) if output.status.success() => true,
        Ok(output) => {
            eprintln!(
                "kyth-save-sync: {label} failed with status {}",
                output.status.code().unwrap_or(-1)
            );
            false
        }
        Err(error) => {
            eprintln!("kyth-save-sync: {label} could not run: {error}");
            false
        }
    }
}

fn gib(bytes: u64) -> f64 {
    bytes as f64 / 1024.0 / 1024.0 / 1024.0
}

fn main() -> std::process::ExitCode {
    let include_flatpak_data = env::args().any(|arg| arg == "--include-flatpak-data");
    let home = env::var_os("HOME").map(PathBuf::from).unwrap_or_default();
    let config = load(config_path(None::<PathBuf>));
    // Fail closed before writing anything: a missing password file means we
    // could neither unlock nor verify the repo we are about to touch.
    if !config.password_file.trim().is_empty() && !Path::new(&config.password_file).is_file() {
        eprintln!(
            "kyth-save-sync: password_file {:?} is missing; refusing to back up to a repo we cannot unlock or verify.",
            config.password_file
        );
        return std::process::ExitCode::FAILURE;
    }
    // External-media preflight: never write a repo into an unmounted stub.
    let mounts = std::fs::read_to_string("/proc/mounts").unwrap_or_default();
    if !repo_mount_ready(&config.repo, &mounts) {
        eprintln!(
            "kyth-save-sync: repo {:?} is on external media that is not mounted; refusing to back up into an unmounted directory.",
            config.repo
        );
        return std::process::ExitCode::FAILURE;
    }
    let mut failed = false;
    let repo = PathBuf::from(&config.repo);
    let _ = std::fs::create_dir_all(&repo);
    if !repo.join("config").exists() {
        let mut init = restic_prefix(&config);
        init.push("init".to_string());
        if !run(&init, 10, "restic init") {
            failed = true;
        }
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
    if targets.is_empty() {
        // Nothing would be written: say so loudly and fail — a silent
        // "backup ran" with zero includes is worse than no backup.
        eprintln!(
            "kyth-save-sync: WARNING: no save data found (no Steam compat prefixes, no Kyth state dirs); nothing was backed up."
        );
        failed = true;
    } else {
        let mut argv = restic_prefix(&config);
        argv.push("backup".to_string());
        argv.extend(targets);
        if !run(&argv, 60, "restic backup") {
            failed = true;
        }
    }
    let remote = config.remote.clone();
    if !remote.is_empty() && home.join(".config/rclone/rclone.conf").exists() {
        // `rclone sync` mirrors deletions: never mirror after a failure, and
        // never mirror an empty repo over a populated remote.
        if failed {
            eprintln!("kyth-save-sync: skipping rclone sync: restic backup failed");
        } else if !repo_has_snapshots(&repo) {
            eprintln!(
                "kyth-save-sync: skipping rclone sync: repo {} holds no snapshots; refusing to mirror an empty repo over the remote",
                repo.display()
            );
            failed = true;
        } else {
            let repo_arg = repo.to_string_lossy().into_owned();
            if !run(
                &[
                    "rclone".to_string(),
                    "sync".to_string(),
                    repo_arg,
                    remote.clone(),
                ],
                120,
                "rclone sync",
            ) {
                failed = true;
            }
        }
    }
    let remote = if remote.is_empty() {
        "none".to_string()
    } else {
        remote
    };
    println!("kyth-save-sync: repo {} remote {remote}", repo.display());
    if failed {
        eprintln!("kyth-save-sync: one or more stages failed");
        std::process::ExitCode::FAILURE
    } else {
        std::process::ExitCode::SUCCESS
    }
}
