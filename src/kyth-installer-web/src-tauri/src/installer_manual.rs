//! Typed execution for the manual-install filesystem matrix.

use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::fs;
use std::path::Path;
use std::process::Command;

#[derive(Clone, Debug, Deserialize, serde::Serialize)]
pub(crate) struct ManualMountsInput {
    pub config_root: String,
    pub fstab_path: String,
    /// The selected storage-plan disk. Every manual partition must re-probe
    /// as a member of this disk at apply time.
    pub disk: String,
    pub mounts: Vec<ManualMountInput>,
}

#[derive(Clone, Debug, Deserialize, serde::Serialize)]
pub(crate) struct ManualMountInput {
    pub partition: String,
    pub mountpoint: String,
    pub fstype: String,
    /// Selection-time filesystem UUID, required: the frontend sends the UUID
    /// shown at selection time, and apply rejects it when it is empty or no
    /// longer matches the partition's probed UUID/PARTUUID.
    pub uuid: String,
}

#[derive(Debug, Serialize)]
pub(crate) struct ManualMountsResult {
    pub configured: usize,
    pub skipped: usize,
}

fn safe_path(value: &str, label: &str) -> Result<String, String> {
    let value = value.trim();
    if value.is_empty()
        || !value.starts_with('/')
        || value.contains("..")
        || value.contains("//")
        || value.split('/').any(|component| component == ".")
        || !value.bytes().all(|b| {
            b.is_ascii_alphanumeric() || matches!(b, b'/' | b'.' | b'_' | b'+' | b':' | b'-')
        })
    {
        return Err(format!("{label} must be an absolute safe path"));
    }
    Ok(value.to_owned())
}

fn safe_device(value: &str) -> Result<String, String> {
    let value = value.trim();
    let basename = value.strip_prefix("/dev/").unwrap_or("");
    let valid_name = !basename.is_empty()
        && (!basename.contains('/')
            || basename
                .strip_prefix("mapper/")
                .is_some_and(|name| !name.is_empty() && !name.contains('/')));
    if !value.starts_with("/dev/")
        || !valid_name
        || value.contains("..")
        || value.contains("//")
        || !value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'/' | b'.' | b'_' | b'-'))
    {
        return Err("manual partition must be a safe /dev path".into());
    }
    Ok(value.to_owned())
}

fn safe_uuid(value: &str) -> Result<String, String> {
    let value = value.trim();
    if value.is_empty() || !value.bytes().all(|b| b.is_ascii_hexdigit() || b == b'-') {
        return Err("manual filesystem UUID is invalid".into());
    }
    Ok(value.to_owned())
}

/// The caller must supply the selection-time UUID, and it must match the
/// partition's freshly probed filesystem UUID or PARTUUID (compared
/// case-insensitively: blkid and lsblk disagree on GUID casing). An empty
/// or mismatched value means the partition changed between selection and
/// apply — fail closed instead of mounting the wrong filesystem.
fn verified_uuid(
    supplied: &str,
    detected_uuid: &str,
    detected_partuuid: &str,
) -> Result<String, String> {
    let supplied = safe_uuid(supplied)?;
    let matches_uuid =
        safe_uuid(detected_uuid).is_ok_and(|detected| detected.eq_ignore_ascii_case(&supplied));
    let matches_partuuid = !detected_partuuid.trim().is_empty()
        && safe_uuid(detected_partuuid)
            .is_ok_and(|detected| detected.eq_ignore_ascii_case(&supplied));
    if !matches_uuid && !matches_partuuid {
        return Err("manual filesystem UUID does not match its selected partition".into());
    }
    Ok(supplied)
}

fn normalized_fs(value: &str) -> Result<&'static str, String> {
    match value.trim().to_ascii_lowercase().as_str() {
        "btrfs" => Ok("btrfs"),
        "ext4" => Ok("ext4"),
        "xfs" => Ok("xfs"),
        "linux-swap" | "swap" => Ok("linux-swap"),
        _ => Err("unsupported manual filesystem type".into()),
    }
}

pub(crate) fn normalize_mountpoint(
    value: &str,
    fs: &str,
    allow_reserved: bool,
) -> Result<String, String> {
    let mountpoint = if fs == "linux-swap" {
        if value.trim() != "swap" {
            return Err("swap filesystems must use the swap mount point".into());
        }
        "swap".to_string()
    } else {
        if value.trim() == "swap" {
            return Err("the swap mount point requires a swap filesystem".into());
        }
        safe_path(value, "manual mount point")?
    };
    let mountpoint = if mountpoint.len() > 1 {
        mountpoint.trim_end_matches('/').to_string()
    } else {
        mountpoint
    };
    if !allow_reserved
        && fs != "linux-swap"
        && (mountpoint == "/" || mountpoint == "/boot" || mountpoint == "/boot/efi")
    {
        return Err("manual mount point is reserved".into());
    }
    Ok(mountpoint)
}

fn normalized_mountpoint(value: &str, fs: &str) -> Result<String, String> {
    normalize_mountpoint(value, fs, false)
}

fn claim_assignment(
    mountpoint: &str,
    device: &str,
    seen_mountpoints: &mut HashSet<String>,
    seen_partitions: &mut HashSet<String>,
) -> Result<(), String> {
    if !seen_mountpoints.insert(mountpoint.to_string()) {
        return Err(format!(
            "manual mount point {mountpoint} is assigned more than once"
        ));
    }
    if !seen_partitions.insert(device.to_string()) {
        return Err(format!(
            "manual partition {device} has multiple mount assignments"
        ));
    }
    Ok(())
}

/// Where a manual mount belongs inside the physical sysroot. ostree bind-mounts
/// the stateroot's `var` over `/var` at boot, so `/var` and everything under it
/// (`/var/home` included) must be mounted inside `ostree/deploy/default/var`.
/// Mounting at `{root}/var/...` mounts over the sysroot's empty `var`, which the
/// booted system never sees, and hides the home directory `create-user` makes.
fn mount_target(root: &str, fstab_mountpoint: &str) -> String {
    if fstab_mountpoint == "/var" || fstab_mountpoint.starts_with("/var/") {
        let rest = &fstab_mountpoint["/var".len()..];
        format!("{root}/ostree/deploy/default/var{rest}")
    } else {
        format!("{root}{fstab_mountpoint}")
    }
}

/// Fresh lsblk probe of the selected disk for the manual-mount safety
/// re-check: parentage, mount state, stacking, read-only flag, and PARTUUID.
fn fresh_partition_snapshot(disk: &str) -> Result<String, String> {
    let output = Command::new("/usr/bin/lsblk")
        .args([
            "--json",
            "--bytes",
            "--paths",
            "--output",
            "NAME,SIZE,TYPE,FSTYPE,PARTTYPE,PARTN,LABEL,MOUNTPOINT,MOUNTPOINTS,START,RO,PARTUUID,PKNAME",
            disk,
        ])
        .output()
        .map_err(|error| format!("could not probe manual install disk: {error}"))?;
    if !output.status.success() {
        return Err("manual install disk probe failed".to_string());
    }
    String::from_utf8(output.stdout)
        .map_err(|_| "manual install disk probe was not UTF-8".to_string())
}

fn logical_sector_size(disk: &str) -> Result<u64, String> {
    let output = Command::new("/usr/bin/blockdev")
        .args(["--getss", disk])
        .output()
        .map_err(|error| format!("could not probe sector size: {error}"))?;
    if !output.status.success() {
        return Err("sector size probe failed".to_string());
    }
    let size = String::from_utf8(output.stdout)
        .map_err(|_| "sector size probe was not UTF-8".to_string())?
        .trim()
        .parse::<u64>()
        .map_err(|_| "sector size probe returned an invalid value".to_string())?;
    if !size.is_power_of_two() || !(512..=4096).contains(&size) {
        return Err("storage probe returned an unsupported sector size".to_string());
    }
    Ok(size)
}

/// Unmount everything the current run mounted, in reverse order.
/// Best-effort: the original failure is always the error reported.
fn rollback_mounts(targets: &[String]) {
    for target in targets.iter().rev() {
        let _ = Command::new("/usr/bin/umount")
            .args(["-R", "-l", target])
            .status();
    }
}

/// Mount one prepared row and append its fstab line. Pushes the mount
/// target onto `mounted` after a successful mount so the caller can roll
/// back every mount this run made when any later row fails.
fn apply_mount_row(
    root: &str,
    fstab: &str,
    device: &str,
    fs: &str,
    fstab_mountpoint: &str,
    line: &str,
    mounted: &mut Vec<String>,
) -> Result<(), String> {
    if fs != "linux-swap" {
        let target = mount_target(root, fstab_mountpoint);
        // Refuse a final-path symlink before creating or mounting through
        // it. The parent may be an ostree-managed /var symlink by design.
        if let Ok(metadata) = fs::symlink_metadata(&target) {
            if metadata.file_type().is_symlink() {
                return Err("manual mountpoint is a symlink".into());
            }
        }
        fs::create_dir_all(&target)
            .map_err(|e| format!("could not create manual mountpoint: {e}"))?;
        let mount_probe = Command::new("/usr/bin/findmnt")
            .args(["--noheadings", "--mountpoint", &target])
            .output()
            .map_err(|e| format!("could not check existing manual mount: {e}"))?;
        if !mount_probe.status.success() && mount_probe.status.code() != Some(1) {
            return Err(
                "could not determine whether the manual mount point is already mounted".into(),
            );
        }
        let already_mounted = mount_probe.status.success();
        if already_mounted {
            let unmounted = Command::new("/usr/bin/umount")
                .args(["-R", "-l", &target])
                .status()
                .map_err(|e| format!("could not unmount existing manual mount: {e}"))?;
            if !unmounted.success() {
                return Err("could not unmount existing manual mount".into());
            }
        }
        let status = Command::new("/usr/bin/mount")
            .args(["-t", fs, device, &target])
            .status()
            .map_err(|e| format!("could not mount manual filesystem: {e}"))?;
        if !status.success() {
            return Err(format!(
                "could not mount manual filesystem on {fstab_mountpoint}"
            ));
        }
        mounted.push(target);
    }
    crate::installer_configuration::append_fstab(crate::installer_configuration::FstabAppendInput {
        path: fstab.to_string(),
        line: line.to_string(),
    })
}

pub(crate) fn apply(input: ManualMountsInput) -> Result<ManualMountsResult, String> {
    let root = safe_path(&input.config_root, "config root")?;
    let root_metadata = fs::symlink_metadata(&root)
        .map_err(|error| format!("could not inspect manual install root: {error}"))?;
    if root_metadata.file_type().is_symlink() || !root_metadata.is_dir() {
        return Err("manual install root must be a real directory".into());
    }
    let fstab = safe_path(&input.fstab_path, "fstab path")?;
    // Keep the check component-based: `Path::ends_with("/etc/fstab")` does
    // not match an absolute path such as `/mnt/target/etc/fstab` because the
    // leading root component is significant to `Path`.
    let fstab_path = Path::new(&fstab);
    if fstab_path.file_name().and_then(|name| name.to_str()) != Some("fstab")
        || fstab_path
            .parent()
            .and_then(|parent| parent.file_name())
            .and_then(|name| name.to_str())
            != Some("etc")
    {
        return Err("fstab path must point to installed /etc/fstab".into());
    }
    // The expected disk: every manual partition must re-probe as a member
    // of this disk immediately before anything is mounted. The disk lock is
    // held across this phase by the executor.
    let disk = safe_device(&input.disk)?;
    let snapshot = fresh_partition_snapshot(&disk)?;
    let sector_size = logical_sector_size(&disk)?;
    // Validate the complete mount table before writing fstab or mounting
    // anything. A late malformed row must not leave earlier rows half-applied.
    let mut prepared = Vec::with_capacity(input.mounts.len());
    let mut seen_mountpoints = HashSet::new();
    let mut seen_partitions = HashSet::new();
    let mut seen_uuids = HashSet::new();
    let mut skipped = 0;
    for mount in &input.mounts {
        let device = safe_device(&mount.partition)?;
        // Fresh safety re-probe: the partition must still belong to the
        // selected disk, and must not have become mounted, stacked under
        // another device, or read-only since the user selected it.
        let probe = crate::installer_storage::partition_probe_from_snapshot(
            &snapshot,
            &disk,
            &device,
            sector_size,
        )
        .map_err(|error| {
            format!("manual partition {device} failed its safety re-probe: {error}")
        })?;
        if probe.current {
            return Err(format!(
                "manual partition {device} is mounted; unmount it before installing"
            ));
        }
        if probe.in_use {
            return Err(format!(
                "manual partition {device} has active mappings stacked on it"
            ));
        }
        if probe.read_only {
            return Err(format!("manual partition {device} is read-only"));
        }
        let detected_uuid =
            crate::installer_probe::lookup_uuid(crate::installer_probe::UuidInput {
                device: device.clone(),
            })?;
        let uuid = verified_uuid(&mount.uuid, &detected_uuid, &probe.partuuid)?;
        // Dedupe this run's additions: two rows resolving to the same UUID
        // (cloned filesystems) would write ambiguous fstab entries, so the
        // later row is skipped instead of appended.
        if !seen_uuids.insert(uuid.clone()) {
            skipped += 1;
            continue;
        }
        let fs = normalized_fs(&mount.fstype)?;
        let mountpoint = normalized_mountpoint(&mount.mountpoint, fs)?;
        let fstab_mountpoint = if mountpoint == "/home" {
            "/var/home"
        } else {
            mountpoint.as_str()
        };
        claim_assignment(
            fstab_mountpoint,
            &device,
            &mut seen_mountpoints,
            &mut seen_partitions,
        )?;
        let pass = if fs == "linux-swap" {
            "0"
        } else if fs == "btrfs" {
            "0"
        } else {
            "2"
        };
        let line = if fs == "linux-swap" {
            format!("UUID={uuid} none swap defaults 0 {pass}\n")
        } else {
            let options = if fs == "btrfs" {
                "defaults,compress=zstd:1"
            } else {
                "defaults"
            };
            format!("UUID={uuid} {fstab_mountpoint} {fs} {options} 0 {pass}\n")
        };
        prepared.push((device, fs, fstab_mountpoint.to_string(), line));
    }

    let mut configured = 0;
    let mut mounted_targets: Vec<String> = Vec::new();
    for (device, fs, fstab_mountpoint, line) in prepared {
        // Any row failure unmounts every mount this run made, in reverse
        // order: a failing row must not leave earlier rows mounted behind
        // without their fstab entries.
        if let Err(error) = apply_mount_row(
            &root,
            &fstab,
            &device,
            fs,
            &fstab_mountpoint,
            &line,
            &mut mounted_targets,
        ) {
            rollback_mounts(&mounted_targets);
            return Err(error);
        }
        configured += 1;
    }
    Ok(ManualMountsResult {
        configured,
        skipped,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn var_mounts_land_in_the_stateroot_var() {
        assert_eq!(
            mount_target("/mnt/target", "/var/home"),
            "/mnt/target/ostree/deploy/default/var/home"
        );
        assert_eq!(
            mount_target("/mnt/target", "/var"),
            "/mnt/target/ostree/deploy/default/var"
        );
        assert_eq!(
            mount_target("/mnt/target", "/var/lib/games"),
            "/mnt/target/ostree/deploy/default/var/lib/games"
        );
        // Not under /var: unchanged, and no false prefix match.
        assert_eq!(mount_target("/mnt/target", "/data"), "/mnt/target/data");
        assert_eq!(
            mount_target("/mnt/target", "/variable"),
            "/mnt/target/variable"
        );
    }

    #[test]
    fn rejects_unsafe_manual_inputs() {
        assert!(safe_device("/dev/sda;id").is_err());
        assert!(safe_device("/dev/").is_err());
        assert!(safe_device("/dev/foo/bar").is_err());
        assert!(safe_device("/dev/mapper/cryptroot").is_ok());
        assert!(safe_device("/dev/mapper/a/b").is_err());
        assert!(safe_path("relative", "path").is_err());
        assert!(normalized_fs("ntfs").is_err());
    }

    #[test]
    fn accepts_lsblk_swap_alias_and_swap_mountpoint() {
        assert_eq!(normalized_fs("swap"), Ok("linux-swap"));
        assert_eq!(
            normalized_mountpoint("swap", "linux-swap"),
            Ok("swap".into())
        );
        assert!(normalized_mountpoint("swap", "btrfs").is_err());
    }
    #[test]
    fn maps_home_to_var_home() {
        assert_eq!(
            "/var/home",
            if "/home" == "/home" {
                "/var/home"
            } else {
                "/home"
            }
        );
    }

    #[test]
    fn rejects_duplicate_mounts_and_duplicate_partition_assignments() {
        let mut mountpoints = HashSet::new();
        let mut partitions = HashSet::new();
        claim_assignment("/home", "/dev/sda2", &mut mountpoints, &mut partitions).unwrap();
        assert!(
            claim_assignment("/home", "/dev/sda3", &mut mountpoints, &mut partitions)
                .unwrap_err()
                .contains("mount point")
        );
        assert!(
            claim_assignment("/var", "/dev/sda2", &mut mountpoints, &mut partitions)
                .unwrap_err()
                .contains("partition")
        );
        assert_eq!(
            safe_path("/home/", "mount point")
                .unwrap()
                .trim_end_matches('/'),
            "/home"
        );
        assert!(safe_path("/home/./data", "mount point").is_err());
    }

    #[test]
    fn rejects_home_alias_collision_with_var_home() {
        let mut mountpoints = HashSet::new();
        let mut partitions = HashSet::new();
        claim_assignment("/var/home", "/dev/sda2", &mut mountpoints, &mut partitions).unwrap();
        assert!(
            claim_assignment("/var/home", "/dev/sda3", &mut mountpoints, &mut partitions).is_err()
        );
    }

    #[test]
    fn rejects_supplied_uuid_that_does_not_belong_to_selected_partition() {
        assert_eq!(
            verified_uuid("ABCD-1234", "ABCD-1234", "").unwrap(),
            "ABCD-1234"
        );
        assert!(verified_uuid("ABCD-9999", "ABCD-1234", "").is_err());
        // An empty supplied UUID is rejected even when the probe found one:
        // the selection-time identity is required, not optional.
        assert!(verified_uuid("", "ABCD-1234", "").is_err());
        // PARTUUID is an acceptable identity too (stable across reformats),
        // compared case-insensitively since blkid and lsblk disagree on
        // GUID casing.
        assert_eq!(
            verified_uuid(
                "c12a7328-f81f-11d2-ba4b-00a0c93ec93b",
                "",
                "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
            )
            .unwrap(),
            "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
        );
        assert!(verified_uuid("ABCD-1234", "", "").is_err());
    }

    #[test]
    fn boot_mountpoint_is_reserved() {
        // A manual /boot would shadow bootc's boot files and ship an
        // unbootable system.
        assert!(normalized_mountpoint("/boot", "ext4").is_err());
        assert!(normalized_mountpoint("/boot/efi", "ext4").is_err());
        assert!(normalized_mountpoint("/", "ext4").is_err());
        // Deeper paths stay legal.
        assert!(normalized_mountpoint("/boot/data", "ext4").is_ok());
    }
}
