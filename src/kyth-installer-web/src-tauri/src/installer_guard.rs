//! Last-moment guards for the selected installation disk.

use std::fs::{File, OpenOptions};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{DirBuilderExt, FileTypeExt, MetadataExt, OpenOptionsExt};

use crate::installer_storage;

fn normalized(disk: &str) -> Result<String, String> {
    crate::installer_plan::normalize_device_path(disk)
        .ok_or_else(|| "selected disk is not a safe device path".to_string())
}

/// A non-bootc mutation keeps both the Kyth operation lease and the raw-device
/// lock alive through backup, mutation, and rollback. Fields are held for RAII.
pub(crate) struct DiskLock {
    _device: File,
    _lease: File,
}

pub(crate) fn acquire_disk_lock(disk: &str) -> Result<DiskLock, String> {
    let disk = normalized(disk)?;
    acquire_mutation_lock_in(
        &disk,
        std::path::Path::new("/run/kyth-installer/disk-locks"),
    )
}

/// Bootc waits for udev between its own storage operations. Keep the same Kyth
/// lease as other mutations, but release the raw-device probe before spawning
/// bootc: udev needs a shared flock on that device in order to drain its queue.
pub(crate) fn acquire_bootc_disk_lock(disk: &str) -> Result<File, String> {
    let disk = normalized(disk)?;
    acquire_disk_lock_in(
        &disk,
        std::path::Path::new("/run/kyth-installer/disk-locks"),
    )
}

fn acquire_mutation_lock_in(disk: &str, lock_dir: &std::path::Path) -> Result<DiskLock, String> {
    let (lease, device) = acquire_lock_pair_in(disk, lock_dir)?;
    Ok(DiskLock {
        _lease: lease,
        _device: device,
    })
}

fn acquire_disk_lock_in(disk: &str, lock_dir: &std::path::Path) -> Result<File, String> {
    let (lease, device) = acquire_lock_pair_in(disk, lock_dir)?;
    drop(device);
    Ok(lease)
}

fn acquire_lock_pair_in(disk: &str, lock_dir: &std::path::Path) -> Result<(File, File), String> {
    let device = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_CLOEXEC)
        .open(disk)
        .map_err(|error| format!("could not lock {disk} for exclusive use: {error}"))?;
    let metadata = device
        .metadata()
        .map_err(|error| format!("could not identify {disk}: {error}"))?;
    // Block-device aliases must share a lease. Regular-file identity also
    // allows the real flock behavior to be tested without touching any disk.
    let key = if metadata.file_type().is_block_device() {
        format!("block-{}.lock", metadata.rdev())
    } else {
        format!("file-{}-{}.lock", metadata.dev(), metadata.ino())
    };
    match std::fs::DirBuilder::new().mode(0o700).create(lock_dir) {
        Ok(()) => {}
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
        Err(error) => return Err(format!("could not create disk lease directory: {error}")),
    }
    let directory = std::fs::symlink_metadata(lock_dir)
        .map_err(|error| format!("could not inspect disk lease directory: {error}"))?;
    if !directory.is_dir()
        || directory.uid() != unsafe { libc::geteuid() }
        || directory.mode() & 0o022 != 0
    {
        return Err(
            "disk lease directory must be owned by the installer and not writable by others".into(),
        );
    }
    let lease = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .mode(0o600)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(lock_dir.join(key))
        .map_err(|error| format!("could not open operation lease for {disk}: {error}"))?;
    let lease_metadata = lease
        .metadata()
        .map_err(|error| format!("could not inspect operation lease: {error}"))?;
    if !lease_metadata.is_file()
        || lease_metadata.uid() != unsafe { libc::geteuid() }
        || lease_metadata.nlink() != 1
        || lease_metadata.mode() & 0o022 != 0
    {
        return Err("disk operation lease must be a private installer-owned regular file".into());
    }
    let lock_failed = unsafe { libc::flock(lease.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0;
    #[cfg(debug_assertions)]
    let bypass_allowed = std::env::var("KYTH_INSTALL_ALLOW_NO_DISK_LOCK").as_deref() == Ok("1");
    #[cfg(not(debug_assertions))]
    let bypass_allowed = false;
    if lock_failed && !bypass_allowed {
        return Err(format!(
            "another process is using {disk}; close other installers and retry"
        ));
    }
    if lock_failed {
        eprintln!("WARNING: KYTH_INSTALL_ALLOW_NO_DISK_LOCK=1 bypassed operation lease for {disk}");
    }
    let device_lock_failed =
        unsafe { libc::flock(device.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0;
    if device_lock_failed && !bypass_allowed {
        return Err(format!(
            "another process is using {disk}; close other installers and retry"
        ));
    }
    if device_lock_failed {
        eprintln!(
            "WARNING: KYTH_INSTALL_ALLOW_NO_DISK_LOCK=1 bypassed exclusive disk lock for {disk}"
        );
    }
    // Do not unlink lease files on drop: another waiter may already have the
    // inode open, and replacing it would permit two independent exclusive locks.
    Ok((lease, device))
}

/// Validate disk ownership from already-captured read-only snapshots.
///
/// `protected_sources` contains mounted device paths, not disk paths. Keeping
/// this function snapshot-based makes the policy independently testable and
/// ensures callers can pair it with a fresh probe immediately before a
/// destructive helper or bootc invocation.
pub(crate) fn validate_target_snapshots(
    disk_snapshot: &str,
    ancestry_snapshot: &str,
    protected_sources: &[String],
    current_source: Option<&str>,
    disk: &str,
) -> Result<(), String> {
    let disk = normalized(disk)?;
    let records = installer_storage::runtime_disks_from_snapshots(
        disk_snapshot,
        ancestry_snapshot,
        protected_sources,
        current_source,
    )?;
    let Some(record) = records.iter().find(|record| record.name == disk) else {
        return Err(format!(
            "selected disk {disk} is unavailable, read-only, or protected by a live mount"
        ));
    };
    if record.current {
        return Err(format!(
            "selected disk {disk} is the current live-session disk"
        ));
    }
    Ok(())
}

fn command_output(program: &str, args: &[&str]) -> Result<String, String> {
    let output = std::process::Command::new(program)
        .args(args)
        .output()
        .map_err(|error| format!("could not run {program}: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "{program} failed with exit code {}: {}",
            output.status.code().unwrap_or(1),
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    String::from_utf8(output.stdout).map_err(|_| format!("{program} returned non-UTF-8 output"))
}

/// Re-probe all disk ancestry and live mounts immediately before mutation.
pub(crate) fn validate_target_disk(disk: &str) -> Result<(), String> {
    validate_target_disk_inner(disk, None)
}

/// Re-probe disk ancestry, live mounts, and the selection-time disk
/// identity immediately before mutation. The executor calls this variant
/// once the storage plan carries the expected disk identity, so a swapped
/// or re-enumerated disk fails closed instead of being written to.
pub(crate) fn validate_target_disk_with_identity(
    disk: &str,
    expected: &installer_storage::DiskIdentity,
) -> Result<(), String> {
    validate_target_disk_inner(disk, Some(expected))
}

fn validate_target_disk_inner(
    disk: &str,
    expected: Option<&installer_storage::DiskIdentity>,
) -> Result<(), String> {
    let disk = normalized(disk)?;
    if let Some(expected) = expected {
        installer_storage::verify_disk_identity(&disk, expected)?;
    }
    let disk_snapshot = command_output(
        "/usr/bin/lsblk",
        &[
            "--json",
            "--bytes",
            "--paths",
            "--output",
            "NAME,SIZE,TYPE,FSTYPE,PARTTYPE,PARTN,LABEL,MOUNTPOINT,MOUNTPOINTS,START,RO,MODEL,TRAN,ROTA,RM,PTTYPE,PKNAME",
        ],
    )?;
    let ancestry_snapshot = command_output(
        "/usr/bin/lsblk",
        &[
            "--json",
            "--bytes",
            "--paths",
            "--output",
            "NAME,PKNAME,TYPE",
        ],
    )?;
    // P8: one batched findmnt call replaces nine sequential per-path probes.
    let mounts = installer_storage::MountTable::parse(&command_output(
        "/usr/bin/findmnt",
        &["--json", "-o", "TARGET,SOURCE"],
    )?)?;
    let protected_sources = mounts.protected_sources();
    let current_source = mounts.current_source();
    validate_target_snapshots(
        &disk_snapshot,
        &ancestry_snapshot,
        &protected_sources,
        current_source.as_deref(),
        &disk,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn snapshots() -> (&'static str, &'static str) {
        (
            r#"{"blockdevices":[
                {"name":"/dev/sda","size":100,"type":"disk","ro":false},
                {"name":"/dev/sdb","size":100,"type":"disk","ro":false}
            ]}"#,
            r#"{"blockdevices":[
                {"name":"/dev/sda","type":"disk"},
                {"name":"/dev/sdb","type":"disk"}
            ]}"#,
        )
    }

    #[test]
    fn non_bootc_mutation_retains_external_writer_exclusion() {
        let temp = tempfile::tempdir().unwrap();
        let disk = temp.path().join("disk");
        File::create(&disk).unwrap();
        let guard = acquire_mutation_lock_in(disk.to_str().unwrap(), &temp.path().join("locks"))
            .expect("mutation guard");
        let external = File::open(&disk).unwrap();
        assert_ne!(
            unsafe { libc::flock(external.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0,
            "partition backup/mutation/rollback must still exclude external writers"
        );
        drop(guard);
        assert_eq!(
            unsafe { libc::flock(external.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
    }

    #[test]
    fn bootc_and_partition_mutations_share_the_operation_lease() {
        let temp = tempfile::tempdir().unwrap();
        let disk = temp.path().join("disk");
        File::create(&disk).unwrap();
        let locks = temp.path().join("locks");
        let bootc = acquire_disk_lock_in(disk.to_str().unwrap(), &locks).unwrap();
        assert!(acquire_mutation_lock_in(disk.to_str().unwrap(), &locks).is_err());
        drop(bootc);
        let _mutation = acquire_mutation_lock_in(disk.to_str().unwrap(), &locks).unwrap();
        assert!(acquire_disk_lock_in(disk.to_str().unwrap(), &locks).is_err());
    }

    #[test]
    fn operation_lock_allows_udev_shared_device_lock() {
        let temp = tempfile::tempdir().unwrap();
        let disk = temp.path().join("disk");
        File::create(&disk).unwrap();
        let _guard = acquire_disk_lock_in(disk.to_str().unwrap(), &temp.path().join("locks"))
            .expect("installer operation lease");
        let udev = File::open(&disk).unwrap();
        let rc = unsafe { libc::flock(udev.as_raw_fd(), libc::LOCK_SH | libc::LOCK_NB) };
        assert_eq!(
            rc, 0,
            "installer must not block udev while bootc waits for settle"
        );
    }

    #[test]
    fn operation_lock_serializes_aliases_and_releases_on_drop() {
        let temp = tempfile::tempdir().unwrap();
        let disk = temp.path().join("disk");
        let alias = temp.path().join("alias");
        File::create(&disk).unwrap();
        std::fs::hard_link(&disk, &alias).unwrap();
        let locks = temp.path().join("locks");
        let guard = acquire_disk_lock_in(disk.to_str().unwrap(), &locks).unwrap();
        assert!(acquire_disk_lock_in(alias.to_str().unwrap(), &locks).is_err());
        drop(guard);
        // Other tests fork concurrently. Their short pre-exec interval may
        // temporarily retain this O_CLOEXEC descriptor after our close.
        let reacquired =
            (0..100).find_map(
                |_| match acquire_disk_lock_in(alias.to_str().unwrap(), &locks) {
                    Ok(lease) => Some(lease),
                    Err(_) => {
                        std::thread::sleep(std::time::Duration::from_millis(10));
                        None
                    }
                },
            );
        assert!(
            reacquired.is_some(),
            "lease was not released after guard drop"
        );
    }

    #[test]
    fn operation_lock_keeps_different_devices_independent() {
        let temp = tempfile::tempdir().unwrap();
        let a = temp.path().join("a");
        let b = temp.path().join("b");
        File::create(&a).unwrap();
        File::create(&b).unwrap();
        let locks = temp.path().join("locks");
        let _a = acquire_disk_lock_in(a.to_str().unwrap(), &locks).unwrap();
        let _b = acquire_disk_lock_in(b.to_str().unwrap(), &locks).unwrap();
    }

    #[test]
    fn operation_lock_rejects_existing_external_device_writer() {
        let temp = tempfile::tempdir().unwrap();
        let disk = temp.path().join("disk");
        let writer = File::create(&disk).unwrap();
        assert_eq!(
            unsafe { libc::flock(writer.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        assert!(acquire_disk_lock_in(disk.to_str().unwrap(), &temp.path().join("locks")).is_err());
    }

    #[test]
    fn operation_lock_rejects_symlinked_lease_directory() {
        let temp = tempfile::tempdir().unwrap();
        let disk = temp.path().join("disk");
        File::create(&disk).unwrap();
        let real = temp.path().join("real");
        std::fs::create_dir(&real).unwrap();
        let alias = temp.path().join("locks");
        std::os::unix::fs::symlink(&real, &alias).unwrap();
        assert!(acquire_disk_lock_in(disk.to_str().unwrap(), &alias).is_err());
    }

    #[test]
    fn operation_lock_rejects_symlinked_lease_file() {
        let temp = tempfile::tempdir().unwrap();
        let disk = temp.path().join("disk");
        let file = File::create(&disk).unwrap();
        let metadata = file.metadata().unwrap();
        let locks = temp.path().join("locks");
        std::fs::DirBuilder::new()
            .mode(0o700)
            .create(&locks)
            .unwrap();
        let key = format!("file-{}-{}.lock", metadata.dev(), metadata.ino());
        std::os::unix::fs::symlink(&disk, locks.join(key)).unwrap();
        assert!(acquire_disk_lock_in(disk.to_str().unwrap(), &locks).is_err());
    }

    #[test]
    fn accepts_unprotected_disk_and_rejects_current_or_protected_disk() {
        let (disk_snapshot, ancestry_snapshot) = snapshots();
        assert!(validate_target_snapshots(
            disk_snapshot,
            ancestry_snapshot,
            &[],
            Some("/dev/sda"),
            "/dev/sdb"
        )
        .is_ok());
        assert!(validate_target_snapshots(
            disk_snapshot,
            ancestry_snapshot,
            &[],
            Some("/dev/sda"),
            "/dev/sda"
        )
        .is_err());
        assert!(validate_target_snapshots(
            disk_snapshot,
            ancestry_snapshot,
            &["/dev/sdb".to_string()],
            Some("/dev/sda"),
            "/dev/sdb"
        )
        .is_err());
    }

    #[test]
    fn rejects_unknown_target_before_probe_policy() {
        let (disk_snapshot, ancestry_snapshot) = snapshots();
        let error = validate_target_snapshots(
            disk_snapshot,
            ancestry_snapshot,
            &[],
            None,
            "../../etc/passwd",
        )
        .expect_err("unsafe target must fail closed");
        assert!(error.contains("safe device path"));
    }
}
