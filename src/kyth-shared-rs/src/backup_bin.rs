//! Native replacement for the Python `kyth-backup` launcher.
//!
//! Restic backup of `/home` (with `--password-file`, `forget --prune`
//! retention, and `check`) plus snapshot-then-send btrfs offload to the
//! first USB target and rclone sync, with the same battery gates. Timeouts
//! match the launcher (10/120/300/120s).
//!
//! Safety rules, all fail-closed:
//! * The restic repo must live on external media (`/run/media/…`,
//!   `/mnt/…`). The historical same-disk default is refused unless the
//!   config records `allow_same_disk = true`.
//! * Any restic failure (init/backup/forget/check) yields a nonzero exit —
//!   a silent "backup ran" with nothing written is worse than no backup.
//! * `rclone sync` mirrors deletions, so it is skipped when any earlier
//!   stage failed, and a repo holding no snapshots is never mirrored over
//!   the remote (a fresh-empty repo would delete good remote snapshots).
//! * USB offload never streams the live subvolume: a read-only snapshot is
//!   frozen first, the snapshot is sent, then the staging snapshot is
//!   deleted (see `system::snapshot::snapshot_then_send_plan`).
//! `backup_preset.py` stays as the Phase 3 fixture.

use std::env;
use std::path::{Path, PathBuf};
use std::time::Duration;

use kyth_shared::system::backup_config::{
    backup_argv, check_argv, config_path, external_mounts_from_proc_mounts, forget_argv, load,
    on_battery, repo_has_snapshots, validate_forget_policy, validate_repo,
};
use kyth_shared::system::process::run_bounded;
use kyth_shared::system::snapshot::{snapshot_then_send_plan, statvfs_usage, validate_send_target};

/// Run `argv` with a timeout, returning true on exit 0. Every failure is
/// reported loudly: the process exit code is the backup's only signal to
/// the timer, so swallowing a failure would fake a healthy backup.
fn run(argv: &[String], timeout_secs: u64, label: &str) -> bool {
    match run_bounded(argv, Duration::from_secs(timeout_secs)) {
        Ok(output) if output.status.success() => true,
        Ok(output) => {
            eprintln!(
                "kyth-backup: {label} failed with status {}",
                output.status.code().unwrap_or(-1)
            );
            false
        }
        Err(error) => {
            eprintln!("kyth-backup: {label} could not run: {error}");
            false
        }
    }
}

fn external_mounts() -> Vec<String> {
    let text = std::fs::read_to_string("/proc/mounts").unwrap_or_default();
    let mut mounts = external_mounts_from_proc_mounts(&text);
    // /run/media subdirectories are per-user removable media even when the
    // exact device mount point is one level up.
    for entry in ["/run/media", "/mnt"] {
        if Path::new(entry).is_dir() && !mounts.iter().any(|mount| mount == entry) {
            mounts.push(entry.to_string());
        }
    }
    mounts
}

fn first_usb_dir() -> Option<PathBuf> {
    let mut groups: Vec<PathBuf> = std::fs::read_dir("/run/media")
        .map(|entries| {
            entries
                .filter_map(|entry| entry.ok().map(|entry| entry.path()))
                .collect()
        })
        .unwrap_or_default();
    groups.sort();
    for group in &groups {
        let mut children: Vec<PathBuf> = std::fs::read_dir(group)
            .map(|entries| {
                entries
                    .filter_map(|entry| entry.ok().map(|entry| entry.path()))
                    .collect()
            })
            .unwrap_or_default();
        children.sort();
        if let Some(first) = children.into_iter().find(|child| child.is_dir()) {
            return Some(first);
        }
    }
    None
}

fn main() -> std::process::ExitCode {
    let home = env::var_os("HOME").map(PathBuf::from).unwrap_or_default();
    let config = load(config_path(None::<PathBuf>));
    if !config.on_battery && on_battery() {
        println!("kyth-backup: on battery, skipping btrfs send");
    }
    // Fail closed on the foot-gun layout before writing anything.
    let mounts = external_mounts();
    let mount_refs: Vec<&str> = mounts.iter().map(String::as_str).collect();
    if let Err(error) = validate_repo(&config, &mount_refs) {
        eprintln!("kyth-backup: {error}");
        return std::process::ExitCode::FAILURE;
    }
    if !config.password_file.trim().is_empty() && !Path::new(&config.password_file).is_file() {
        eprintln!(
            "kyth-backup: password_file {:?} is missing; refusing to back up to a repo we cannot unlock or verify.",
            config.password_file
        );
        return std::process::ExitCode::FAILURE;
    }
    let mut failed = false;
    // A malformed retention policy must fail closed before restic runs: it is
    // appended raw to the forget argv, so an unknown flag could silently
    // change what `forget --prune` keeps.
    if let Err(error) = validate_forget_policy(&config.forget_policy) {
        eprintln!("kyth-backup: {error}");
        return std::process::ExitCode::FAILURE;
    }
    let repo = PathBuf::from(&config.repo);
    let _ = std::fs::create_dir_all(&repo);
    if !repo.join("config").exists() {
        let mut init = vec![
            "restic".to_string(),
            "init".to_string(),
            "--repo".to_string(),
            repo.to_string_lossy().into_owned(),
        ];
        if !config.password_file.trim().is_empty() {
            init.push("--password-file".to_string());
            init.push(config.password_file.clone());
        }
        if !run(&init, 10, "restic init") {
            failed = true;
        }
    }
    if !run(
        &backup_argv(&config, &home.to_string_lossy()),
        120,
        "restic backup",
    ) {
        failed = true;
    } else {
        // Retention + integrity only make sense against a backup that
        // succeeded; a failed backup must not prune good snapshots away.
        if !run(&forget_argv(&config), 120, "restic forget --prune") {
            failed = true;
        }
        if !run(&check_argv(&config), 120, "restic check") {
            failed = true;
        }
    }
    if config.btrfs_send && !on_battery() {
        if let Some(usb) = first_usb_dir() {
            // Capacity/filesystem gate before streaming: the send stream can
            // only land on Btrfs with room to hold it, and the alphabetical
            // first dir may be the wrong stick or a non-btrfs volume.
            let target_ok = match statvfs_usage(&usb) {
                Some((magic, free_bytes)) => {
                    match validate_send_target(&usb.to_string_lossy(), magic, free_bytes) {
                        Ok(()) => true,
                        Err(error) => {
                            eprintln!("kyth-backup: skipping btrfs send: {error}");
                            failed = true;
                            false
                        }
                    }
                }
                None => {
                    eprintln!(
                        "kyth-backup: skipping btrfs send: cannot stat target {}",
                        usb.display()
                    );
                    failed = true;
                    false
                }
            };
            if target_ok {
                // Snapshot-then-send: freeze a read-only snapshot of /home,
                // stream the snapshot (never the live subvolume) to USB, then
                // delete the staging snapshot.
                let plan = snapshot_then_send_plan("/home", "kyth-send", &usb.to_string_lossy());
                let staged = run(&plan.snapshot_argv, 120, "btrfs snapshot for send");
                if !staged {
                    failed = true;
                } else {
                    if !run(&plan.send_argv, 300, "btrfs send to USB") {
                        failed = true;
                    }
                    if !run(&plan.cleanup_argv, 120, "btrfs send staging cleanup") {
                        failed = true;
                    }
                }
            }
        }
    }
    if !config.remote.is_empty() && home.join(".config/rclone/rclone.conf").exists() {
        // `rclone sync` mirrors deletions: syncing after a failed backup, or
        // syncing a fresh-empty repo, would delete good remote snapshots.
        if failed {
            eprintln!("kyth-backup: skipping rclone sync: earlier backup stages failed");
        } else if !repo_has_snapshots(&repo) {
            eprintln!(
                "kyth-backup: skipping rclone sync: repo {} holds no snapshots; \
refusing to mirror an empty repo over the remote",
                repo.display()
            );
            failed = true;
        } else if !run(
            &[
                "rclone".to_string(),
                "sync".to_string(),
                repo.to_string_lossy().into_owned(),
                config.remote.clone(),
            ],
            120,
            "rclone sync",
        ) {
            failed = true;
        }
    }
    println!("kyth-backup: repo {}", repo.display());
    if failed {
        eprintln!("kyth-backup: one or more stages failed");
        std::process::ExitCode::FAILURE
    } else {
        std::process::ExitCode::SUCCESS
    }
}
