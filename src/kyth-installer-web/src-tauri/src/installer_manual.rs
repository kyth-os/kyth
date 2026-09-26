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
    pub mounts: Vec<ManualMountInput>,
}

#[derive(Clone, Debug, Deserialize, serde::Serialize)]
pub(crate) struct ManualMountInput {
    pub partition: String,
    pub mountpoint: String,
    pub fstype: String,
    #[serde(default)]
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

fn normalized_fs(value: &str) -> Result<&'static str, String> {
    match value.trim().to_ascii_lowercase().as_str() {
        "btrfs" => Ok("btrfs"),
        "ext4" => Ok("ext4"),
        "xfs" => Ok("xfs"),
        "linux-swap" | "swap" => Ok("linux-swap"),
        _ => Err("unsupported manual filesystem type".into()),
    }
}

fn normalized_mountpoint(value: &str, fs: &str) -> Result<String, String> {
    let mountpoint = if fs == "linux-swap" && value.trim() == "swap" {
        "swap".to_string()
    } else {
        safe_path(value, "manual mount point")?
    };
    let mountpoint = if mountpoint.len() > 1 {
        mountpoint.trim_end_matches('/').to_string()
    } else {
        mountpoint
    };
    if fs != "linux-swap" && (mountpoint == "/" || mountpoint == "/boot/efi") {
        return Err("manual mount point is reserved".into());
    }
    Ok(mountpoint)
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
    // Validate the complete mount table before writing fstab or mounting
    // anything. A late malformed row must not leave earlier rows half-applied.
    let mut prepared = Vec::with_capacity(input.mounts.len());
    let mut seen_mountpoints = HashSet::new();
    let mut seen_partitions = HashSet::new();
    for mount in input.mounts {
        let device = safe_device(&mount.partition)?;
        let uuid = if mount.uuid.trim().is_empty() {
            crate::installer_probe::lookup_uuid(crate::installer_probe::UuidInput {
                device: device.clone(),
            })?
        } else {
            safe_uuid(&mount.uuid)?
        };
        let fs = normalized_fs(&mount.fstype)?;
        let mountpoint = normalized_mountpoint(&mount.mountpoint, fs)?;
        claim_assignment(
            &mountpoint,
            &device,
            &mut seen_mountpoints,
            &mut seen_partitions,
        )?;
        let fstab_mountpoint = if mountpoint == "/home" {
            "/var/home"
        } else {
            mountpoint.as_str()
        };
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
    let skipped = 0;
    for (device, fs, fstab_mountpoint, line) in prepared {
        if fs != "linux-swap" {
            let target = format!("{root}{fstab_mountpoint}");
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
                .args(["-t", fs, &device, &target])
                .status()
                .map_err(|e| format!("could not mount manual filesystem: {e}"))?;
            if !status.success() {
                return Err(format!(
                    "could not mount manual filesystem on {fstab_mountpoint}"
                ));
            }
        }
        if let Err(error) = crate::installer_configuration::append_fstab(
            crate::installer_configuration::FstabAppendInput {
                path: fstab.clone(),
                line,
            },
        ) {
            // Do not leave a mounted filesystem behind without its fstab
            // entry; report the durable configuration failure to the caller.
            if fs != "linux-swap" {
                let target = format!("{root}{fstab_mountpoint}");
                let rollback = Command::new("/usr/bin/umount")
                    .args(["-R", "-l", &target])
                    .status();
                if !rollback.is_ok_and(|status| status.success()) {
                    return Err(format!(
                        "{error}; could not unmount {target} after the fstab update failed"
                    ));
                }
            }
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
}
