//! Typed, root-only execution plans for non-interactive disk operations.
//!
//! The native executor chooses when an operation is needed but never accepts
//! caller-provided argv. Every accepted request maps to one fixed executable
//! and one fixed argv shape.

use serde::Deserialize;
use std::path::Path;
use std::process::Command;

use crate::installer_plan::normalize_device_path;

const MAX_LABEL_BYTES: usize = 128;
const MAX_PATH_BYTES: usize = 4096;
const DEFAULT_SECTOR_SIZE: u64 = 512;

#[derive(Debug, Deserialize)]
#[serde(tag = "operation", rename_all = "snake_case")]
pub(crate) enum DiskOperationInput {
    BackupTable {
        disk: String,
        backup_path: String,
    },
    RestoreTable {
        disk: String,
        backup_path: String,
    },
    CreateLabel {
        disk: String,
        table_type: String,
    },
    CreatePartition {
        disk: String,
        start: u64,
        size: u64,
        fs: String,
        label: String,
        #[serde(default = "default_sector_size")]
        sector_size: u64,
    },
    CreateUnformattedPartition {
        disk: String,
        start: u64,
        size: u64,
        label: String,
        #[serde(default = "default_sector_size")]
        sector_size: u64,
    },
    DeletePartition {
        disk: String,
        part_num: u32,
        expected_partuuid: String,
    },
    ResizePartition {
        disk: String,
        part_num: u32,
        start: u64,
        new_size: u64,
        #[serde(default = "default_sector_size")]
        sector_size: u64,
        expected_partuuid: String,
    },
    FilesystemCheck {
        device: String,
    },
    FilesystemResize {
        device: String,
        fs: String,
        new_size_bytes: u64,
        stage: String,
    },
    MountFilesystem {
        device: String,
        mountpoint: String,
        #[serde(default)]
        options: Vec<String>,
        #[serde(default)]
        bind: bool,
    },
    UnmountFilesystem {
        mountpoint: String,
        #[serde(default)]
        recursive: bool,
        #[serde(default)]
        lazy: bool,
    },
    SetPartitionFlag {
        disk: String,
        part_num: u32,
        flag: String,
        #[serde(default = "default_true")]
        enabled: bool,
        expected_partuuid: String,
    },
    FormatFilesystem {
        device: String,
        fs: String,
        label: String,
        /// The install plan's selected disk (e.g. `/dev/sda`). build_mkfs
        /// fails closed unless the target partition's parent disk matches.
        expected_disk: String,
    },
    BtrfsSubvolumeCreate {
        mountpoint: String,
        name: String,
    },
    BtrfsSubvolumeSetDefault {
        mountpoint: String,
        name: String,
    },
    EnsureDirectory {
        path: String,
    },
}

impl DiskOperationInput {
    pub(crate) fn backup_path(&self) -> Option<&str> {
        match self {
            Self::BackupTable { backup_path, .. } => Some(backup_path),
            _ => None,
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
pub(crate) struct DiskPlan {
    pub(crate) argv: Vec<String>,
    pub(crate) timeout_seconds: u64,
    pub(crate) needs_confirmation: bool,
}

/// Make a completed partition-table backup durable before the caller can
/// mutate the disk. This belongs next to the root-only backup operation so a
/// compatibility caller cannot accidentally persist an unsynced snapshot.
pub(crate) fn sync_backup(path: &str) -> Result<(), String> {
    let file = std::fs::File::open(path)
        .map_err(|error| format!("could not open partition backup for syncing: {error}"))?;
    file.sync_all()
        .map_err(|error| format!("could not sync partition backup: {error}"))?;
    let parent = std::path::Path::new(path)
        .parent()
        .ok_or_else(|| "partition backup has no parent directory".to_string())?;
    let directory = std::fs::File::open(parent)
        .map_err(|error| format!("could not open partition backup directory: {error}"))?;
    directory
        .sync_all()
        .map_err(|error| format!("could not sync partition backup directory: {error}"))
}

/// Partition-table backup argv for a known table type. GPT uses sgdisk's
/// native backup format; MBR ("dos") uses sfdisk's dump, which sgdisk cannot
/// read or write. sfdisk emits the dump on stdout, so the MBR plan shells
/// the redirection into the backup file; both interpolated paths pass
/// strict validators that exclude every shell metacharacter, and the
/// positional parameters stay double-quoted.
fn table_backup_plan(
    disk: String,
    backup_path: String,
    table_type: &str,
    sfdisk: Option<&str>,
) -> Result<DiskPlan, String> {
    match table_type {
        "gpt" => Ok(DiskPlan {
            argv: vec![
                "/usr/sbin/sgdisk".to_string(),
                "--backup".to_string(),
                safe_absolute_path(&backup_path, "backup path")?,
                required_device(&disk, "disk")?,
            ],
            timeout_seconds: 30,
            needs_confirmation: false,
        }),
        "dos" => {
            let sfdisk = sfdisk.ok_or_else(|| {
                "sfdisk is required for MBR partition table backup but is not installed."
                    .to_string()
            })?;
            Ok(DiskPlan {
                argv: vec![
                    "/bin/sh".to_string(),
                    "-c".to_string(),
                    format!("exec {sfdisk} --dump \"$1\" > \"$2\""),
                    "kyth-sfdisk-dump".to_string(),
                    required_device(&disk, "disk")?,
                    safe_absolute_path(&backup_path, "backup path")?,
                ],
                timeout_seconds: 30,
                needs_confirmation: false,
            })
        }
        _ => Err(format!("unsupported partition table type: {table_type}")),
    }
}

/// Partition-table restore argv for a known table type. Mirrors
/// [`table_backup_plan`]: sgdisk's `--load-backup` for GPT, and for MBR a
/// dump script piped back into sfdisk, which reads the table description
/// from stdin. `--force` keeps the non-interactive restore from prompting,
/// matching the sgdisk path.
fn table_restore_plan(
    disk: String,
    backup_path: String,
    table_type: &str,
    sfdisk: Option<&str>,
) -> Result<DiskPlan, String> {
    match table_type {
        "gpt" => Ok(DiskPlan {
            argv: vec![
                "/usr/sbin/sgdisk".to_string(),
                "--load-backup".to_string(),
                safe_absolute_path(&backup_path, "backup path")?,
                required_device(&disk, "disk")?,
            ],
            timeout_seconds: 60,
            needs_confirmation: false,
        }),
        "dos" => {
            let sfdisk = sfdisk.ok_or_else(|| {
                "sfdisk is required for MBR partition table restore but is not installed."
                    .to_string()
            })?;
            Ok(DiskPlan {
                argv: vec![
                    "/bin/sh".to_string(),
                    "-c".to_string(),
                    format!("exec {sfdisk} --force \"$1\" < \"$2\""),
                    "kyth-sfdisk-load".to_string(),
                    required_device(&disk, "disk")?,
                    safe_absolute_path(&backup_path, "backup path")?,
                ],
                timeout_seconds: 60,
                needs_confirmation: false,
            })
        }
        _ => Err(format!("unsupported partition table type: {table_type}")),
    }
}

fn default_sector_size() -> u64 {
    DEFAULT_SECTOR_SIZE
}

fn default_true() -> bool {
    true
}

fn required_device(raw: &str, label: &str) -> Result<String, String> {
    let device = normalize_device_path(raw)
        .filter(|value| value.len() > "/dev/".len() && !value.contains("//"))
        .ok_or_else(|| format!("{label} must be a safe device path."))?;
    Ok(device)
}

fn safe_absolute_path(raw: &str, label: &str) -> Result<String, String> {
    let value = raw.trim();
    if value.is_empty()
        || value.len() > MAX_PATH_BYTES
        || !value.starts_with('/')
        || value.contains("..")
        || value.contains("//")
        || !value.bytes().all(|byte| {
            byte.is_ascii_alphanumeric() || matches!(byte, b'/' | b'.' | b'_' | b'+' | b':' | b'-')
        })
    {
        return Err(format!("{label} must be an absolute safe path."));
    }
    Ok(value.to_string())
}

fn safe_mountpoint(raw: &str) -> Result<String, String> {
    safe_absolute_path(raw, "mount point")
}

fn safe_btrfs_subvolume_name(raw: &str) -> Result<String, String> {
    let name = raw.trim();
    if !matches!(name, "@" | "@home") {
        return Err("unsupported Btrfs subvolume name".to_string());
    }
    Ok(name.to_string())
}

fn safe_mount_options(options: &[String]) -> Result<Vec<String>, String> {
    if options.len() > 8 {
        return Err("mount options are too numerous".to_string());
    }
    options
        .iter()
        .map(|option| {
            if option.is_empty()
                || option.len() > 128
                || !option.bytes().all(|byte| {
                    byte.is_ascii_alphanumeric()
                        || matches!(byte, b'=' | b':' | b'.' | b'_' | b'+' | b'@' | b'-')
                })
            {
                return Err("mount options contain unsupported characters".to_string());
            }
            Ok(option.clone())
        })
        .collect()
}

fn safe_label(raw: String) -> Result<String, String> {
    if raw.len() > MAX_LABEL_BYTES || raw.chars().any(char::is_control) {
        return Err("partition label is empty or contains unsafe characters.".to_string());
    }
    Ok(raw)
}

fn normalized_name(raw: &str) -> String {
    raw.trim().to_ascii_lowercase()
}

/// Run a fixed read-only lsblk probe. `disk` scopes the probe to one disk;
/// `None` probes the whole system (needed to resolve a partition's parent
/// disk, since a device-scoped probe omits the parent itself).
fn lsblk_snapshot(disk: Option<&str>, columns: &str) -> Result<String, String> {
    let mut args = vec!["--json", "--bytes", "--paths", "--output", columns];
    if let Some(disk) = disk {
        args.push(disk);
    }
    let output = Command::new("/usr/bin/lsblk")
        .args(args)
        .output()
        .map_err(|error| format!("could not probe disk state: {error}"))?;
    if !output.status.success() {
        return Err("disk state probe failed.".to_string());
    }
    String::from_utf8(output.stdout).map_err(|_| "disk state probe was not UTF-8.".to_string())
}

/// Logical sector size from `blockdev --getss`, validated the same way the
/// storage layer validates it: power of two, 512..=4096, fail closed.
pub(crate) fn logical_sector_size(disk: &str) -> Result<u64, String> {
    let output = Command::new("/usr/bin/blockdev")
        .args(["--getss", disk])
        .output()
        .map_err(|error| format!("could not probe sector size: {error}"))?;
    if !output.status.success() {
        return Err("sector size probe failed.".to_string());
    }
    let size = String::from_utf8(output.stdout)
        .map_err(|_| "sector size probe was not UTF-8.".to_string())?
        .trim()
        .parse::<u64>()
        .map_err(|_| "sector size probe returned an invalid value.".to_string())?;
    if !size.is_power_of_two() || !(512..=4096).contains(&size) {
        return Err("storage probe returned an unsupported sector size.".to_string());
    }
    Ok(size)
}

fn safe_partuuid(raw: &str) -> Result<String, String> {
    let value = raw.trim();
    if value.is_empty()
        || value.len() > 128
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() || byte == b'-')
    {
        return Err("expected partition UUID is invalid.".to_string());
    }
    Ok(value.to_string())
}

/// Assert the caller's selection-time PARTUUID still matches the partition
/// number in a fresh probe. A bare partition number is a TOCTOU hazard: the
/// kernel may have renumbered partitions since the user selected one.
/// Callers must invoke `build_plan` for these operations while holding the
/// disk lock; the probe-then-act window is only safe under that lock.
fn assert_partition_identity(
    disk: &str,
    part_num: u32,
    expected_partuuid: &str,
) -> Result<(), String> {
    let expected = safe_partuuid(expected_partuuid)?;
    let disk = required_device(disk, "disk")?;
    let snapshot = lsblk_snapshot(Some(&disk), "NAME,PARTN,PARTUUID,TYPE")?;
    let actual =
        crate::installer_storage::partuuid_for_partition_number(&snapshot, &disk, part_num)?;
    if !actual.eq_ignore_ascii_case(&expected) {
        return Err(
            "partition identity changed since selection; refusing to operate on a different partition."
                .to_string(),
        );
    }
    Ok(())
}

/// Read the disk's partition-table type from a fresh lsblk probe: "gpt" or
/// "dos". Anything else (no table, exotic table) fails closed rather than
/// backing up with the wrong tool.
fn probe_partition_table_type(disk: &str) -> Result<String, String> {
    let disk = required_device(disk, "disk")?;
    let output = Command::new("/usr/bin/lsblk")
        .args(["--nodeps", "--noheadings", "--output", "PTTYPE", &disk])
        .output()
        .map_err(|error| format!("could not probe partition table type: {error}"))?;
    if !output.status.success() {
        return Err("partition table type probe failed.".to_string());
    }
    let table_type = String::from_utf8(output.stdout)
        .map_err(|_| "partition table type probe was not UTF-8.".to_string())?
        .trim()
        .to_ascii_lowercase();
    match table_type.as_str() {
        "gpt" | "dos" => Ok(table_type),
        _ => Err("disk has no recognized partition table; refusing to back it up.".to_string()),
    }
}

/// Locate sfdisk for MBR table backup/restore. sgdisk only understands GPT;
/// without sfdisk an MBR table cannot be backed up, so the caller fails
/// closed instead of writing an sgdisk backup of a DOS table.
fn sfdisk_binary() -> Result<&'static str, String> {
    ["/usr/sbin/sfdisk", "/usr/bin/sfdisk"]
        .into_iter()
        .find(|path| Path::new(path).exists())
        .ok_or_else(|| {
            "sfdisk is required for MBR partition table backup but is not installed.".to_string()
        })
}

/// Partitions are aligned to 1 MiB (or the sector size, whichever is
/// larger), matching the free-region alignment in `installer_storage`.
/// Sector-granular starts confuse parted/GRUB and waste SSD erase blocks.
const PARTITION_ALIGN_BYTES: u64 = 1024 * 1024;

fn partition_end(start: u64, size: u64, sector_size: u64) -> Result<u64, String> {
    if sector_size == 0 || !sector_size.is_power_of_two() || !(512..=4096).contains(&sector_size) {
        return Err("partition sector size is unsupported.".to_string());
    }
    let align = sector_size.max(PARTITION_ALIGN_BYTES);
    if start == 0 || size < align {
        return Err("partition start or size is invalid.".to_string());
    }
    if start % align != 0 || size % align != 0 {
        return Err("partition geometry is not aligned to 1 MiB.".to_string());
    }
    start
        .checked_add(size - sector_size)
        .ok_or_else(|| "partition geometry overflows.".to_string())
}

fn parted_device(
    disk: String,
    args: Vec<String>,
    timeout_seconds: u64,
) -> Result<DiskPlan, String> {
    let disk = required_device(&disk, "disk")?;
    Ok(DiskPlan {
        argv: std::iter::once("/usr/sbin/parted".to_string())
            .chain(std::iter::once("-s".to_string()))
            .chain(std::iter::once(disk))
            .chain(args)
            .collect(),
        timeout_seconds,
        needs_confirmation: false,
    })
}

fn interactive_parted_device(
    disk: String,
    args: Vec<String>,
    timeout_seconds: u64,
) -> Result<DiskPlan, String> {
    let disk = required_device(&disk, "disk")?;
    Ok(DiskPlan {
        argv: std::iter::once("/usr/sbin/parted".to_string())
            .chain(std::iter::once("---pretend-input-tty".to_string()))
            .chain(std::iter::once(disk))
            .chain(args)
            .collect(),
        timeout_seconds,
        needs_confirmation: true,
    })
}

/// Guarded mkfs entry point: re-validates the target against a fresh probe
/// immediately before building the mkfs argv, so an ESP, a mounted or
/// stacked partition, or a device that is not a partition of a known disk
/// can never be formatted even if a future caller skips validation.
///
/// The minimum-size and foreign-filesystem gates stay on the guided
/// alongside/manual commit path (`validate_replace_target`): the manual
/// partition editor formats small ESPs (before the `esp` flag is set) and
/// existing filesystems on explicit user request, and a blanket gate here
/// would break those legitimate flows.
fn build_mkfs(
    device: String,
    fs: String,
    label: String,
    expected_disk: String,
) -> Result<DiskPlan, String> {
    let device = required_device(&device, "filesystem device")?;
    let expected_disk = required_device(&expected_disk, "expected disk")?;
    let snapshot = lsblk_snapshot(
        None,
        "NAME,SIZE,TYPE,FSTYPE,PARTTYPE,PARTN,LABEL,MOUNTPOINT,MOUNTPOINTS,START,RO,PKNAME",
    )?;
    let disk = crate::installer_storage::parent_disk_in_snapshot(&snapshot, &device)?
        .ok_or_else(|| "mkfs target is not on a known disk.".to_string())?;
    // M14: the target partition's parent disk must be the install plan's
    // selected disk. Re-validating "not ESP, not mounted, is a partition of
    // a known disk" is not enough: a stale device path could otherwise
    // format a partition on the wrong disk.
    if disk != expected_disk {
        return Err(
            "mkfs target is not on the install plan's selected disk; refusing to format."
                .to_string(),
        );
    }
    let sector_size = logical_sector_size(&disk)?;
    crate::installer_storage::validate_format_target(&snapshot, &disk, &device, sector_size)?;
    build_mkfs_plan(device, fs, label)
}

fn build_mkfs_plan(device: String, fs: String, label: String) -> Result<DiskPlan, String> {
    let device = required_device(&device, "filesystem device")?;
    let fs = normalized_name(&fs);
    let label = safe_label(label)?;
    let (binary, mut args): (&str, Vec<String>) = match fs.as_str() {
        "btrfs" => ("/usr/sbin/mkfs.btrfs", vec!["-f".to_string()]),
        "ext4" => ("/usr/sbin/mkfs.ext4", vec!["-F".to_string()]),
        "xfs" => ("/usr/sbin/mkfs.xfs", vec!["-f".to_string()]),
        "fat32" => ("/usr/sbin/mkfs.fat", vec!["-F32".to_string()]),
        "linux-swap" => ("/usr/sbin/mkswap", Vec::new()),
        _ => return Err(format!("unsupported filesystem type: {fs}")),
    };
    if !label.is_empty() {
        args.extend([if fs == "fat32" { "-n" } else { "-L" }.to_string(), label]);
    }
    args.push(device);
    Ok(DiskPlan {
        argv: std::iter::once(binary.to_string()).chain(args).collect(),
        timeout_seconds: if fs == "btrfs" { 300 } else { 120 },
        needs_confirmation: false,
    })
}

fn build_filesystem_resize(
    device: String,
    fs: String,
    new_size_bytes: u64,
    stage: String,
) -> Result<DiskPlan, String> {
    let device = required_device(&device, "filesystem device")?;
    if new_size_bytes == 0 {
        return Err("filesystem resize size must be positive.".to_string());
    }
    let fs = normalized_name(&fs);
    let stage = normalized_name(&stage);
    match (fs.as_str(), stage.as_str()) {
        ("ntfs" | "ntfs3", "check") => Ok(DiskPlan {
            argv: vec![
                "/usr/sbin/ntfsresize".to_string(),
                "--check".to_string(),
                device,
            ],
            timeout_seconds: 240,
            needs_confirmation: false,
        }),
        ("ntfs" | "ntfs3", "info") => Ok(DiskPlan {
            argv: vec![
                "/usr/sbin/ntfsresize".to_string(),
                "--info".to_string(),
                device,
            ],
            timeout_seconds: 120,
            needs_confirmation: false,
        }),
        ("ntfs" | "ntfs3", "dry_run") => Ok(DiskPlan {
            argv: vec![
                "/usr/sbin/ntfsresize".to_string(),
                "--no-action".to_string(),
                "--size".to_string(),
                new_size_bytes.to_string(),
                device,
            ],
            timeout_seconds: 240,
            needs_confirmation: false,
        }),
        ("ntfs" | "ntfs3", "resize") => Ok(DiskPlan {
            argv: vec![
                "/usr/sbin/ntfsresize".to_string(),
                "--size".to_string(),
                new_size_bytes.to_string(),
                device,
            ],
            timeout_seconds: 1800,
            needs_confirmation: true,
        }),
        ("ext2" | "ext3" | "ext4", "resize") => {
            let size_kib = std::cmp::max(1, new_size_bytes / 1024);
            Ok(DiskPlan {
                argv: vec![
                    "/usr/sbin/resize2fs".to_string(),
                    device,
                    format!("{size_kib}K"),
                ],
                timeout_seconds: 1800,
                needs_confirmation: false,
            })
        }
        ("btrfs", "resize") => Ok(DiskPlan {
            argv: vec![
                "/usr/sbin/btrfs".to_string(),
                "filesystem".to_string(),
                "resize".to_string(),
                new_size_bytes.to_string(),
                device,
            ],
            timeout_seconds: 1800,
            needs_confirmation: false,
        }),
        _ => Err(format!(
            "unsupported filesystem resize operation: {fs}/{stage}"
        )),
    }
}

/// Pure argv builders for the identity-asserted partition operations. The
/// `build_plan` arms assert the caller's selection-time PARTUUID against a
/// fresh probe first, then delegate here, keeping the argv shapes
/// unit-testable without devices.
fn build_delete_partition(disk: String, part_num: u32) -> Result<DiskPlan, String> {
    if part_num == 0 {
        return Err("partition number must be positive.".to_string());
    }
    parted_device(disk, vec!["rm".to_string(), part_num.to_string()], 60)
}

fn build_resize_partition(
    disk: String,
    part_num: u32,
    start: u64,
    new_size: u64,
    sector_size: u64,
) -> Result<DiskPlan, String> {
    if part_num == 0 {
        return Err("partition number must be positive.".to_string());
    }
    let end = partition_end(start, new_size, sector_size)?;
    interactive_parted_device(
        disk,
        vec![
            "unit".to_string(),
            "B".to_string(),
            "resizepart".to_string(),
            part_num.to_string(),
            format!("{end}B"),
        ],
        120,
    )
}

fn build_set_partition_flag(
    disk: String,
    part_num: u32,
    flag: String,
    enabled: bool,
) -> Result<DiskPlan, String> {
    if part_num == 0 {
        return Err("partition number must be positive.".to_string());
    }
    let flag = normalized_name(&flag);
    if !matches!(flag.as_str(), "bios_grub" | "esp") {
        return Err(format!("unsupported partition flag: {flag}"));
    }
    parted_device(
        disk,
        vec![
            "set".to_string(),
            part_num.to_string(),
            flag,
            if enabled { "on" } else { "off" }.to_string(),
        ],
        60,
    )
}

pub(crate) fn build_plan(input: DiskOperationInput) -> Result<DiskPlan, String> {
    match input {
        DiskOperationInput::BackupTable { disk, backup_path } => {
            let table_type = probe_partition_table_type(&disk)?;
            let sfdisk = match table_type.as_str() {
                "dos" => Some(sfdisk_binary()?),
                _ => None,
            };
            table_backup_plan(disk, backup_path, &table_type, sfdisk)
        }
        DiskOperationInput::RestoreTable { disk, backup_path } => {
            let table_type = probe_partition_table_type(&disk)?;
            let sfdisk = match table_type.as_str() {
                "dos" => Some(sfdisk_binary()?),
                _ => None,
            };
            table_restore_plan(disk, backup_path, &table_type, sfdisk)
        }
        DiskOperationInput::CreateLabel { disk, table_type } => {
            let table_type = normalized_name(&table_type);
            if !matches!(table_type.as_str(), "gpt" | "msdos") {
                return Err(format!("unsupported partition table type: {table_type}"));
            }
            parted_device(disk, vec!["mklabel".to_string(), table_type], 30)
        }
        DiskOperationInput::CreatePartition {
            disk,
            start,
            size,
            fs,
            label,
            sector_size,
        } => {
            let fs = normalized_name(&fs);
            if !matches!(
                fs.as_str(),
                "btrfs" | "ext4" | "xfs" | "fat32" | "linux-swap"
            ) {
                return Err(format!("unsupported filesystem type: {fs}"));
            }
            let label = safe_label(label)?;
            let end = partition_end(start, size, sector_size)?;
            parted_device(
                disk,
                vec![
                    "unit".to_string(),
                    "B".to_string(),
                    "mkpart".to_string(),
                    if label.is_empty() {
                        "partition".to_string()
                    } else {
                        label
                    },
                    fs,
                    format!("{start}B"),
                    format!("{end}B"),
                ],
                120,
            )
        }
        DiskOperationInput::CreateUnformattedPartition {
            disk,
            start,
            size,
            label,
            sector_size,
        } => {
            let end = partition_end(start, size, sector_size)?;
            parted_device(
                disk,
                vec![
                    "unit".to_string(),
                    "B".to_string(),
                    "mkpart".to_string(),
                    safe_label(label)?,
                    format!("{start}B"),
                    format!("{end}B"),
                ],
                120,
            )
        }
        DiskOperationInput::DeletePartition {
            disk,
            part_num,
            expected_partuuid,
        } => {
            assert_partition_identity(&disk, part_num, &expected_partuuid)?;
            build_delete_partition(disk, part_num)
        }
        DiskOperationInput::ResizePartition {
            disk,
            part_num,
            start,
            new_size,
            sector_size,
            expected_partuuid,
        } => {
            assert_partition_identity(&disk, part_num, &expected_partuuid)?;
            build_resize_partition(disk, part_num, start, new_size, sector_size)
        }
        DiskOperationInput::FilesystemCheck { device } => {
            let device = required_device(&device, "filesystem device")?;
            Ok(DiskPlan {
                argv: vec![
                    "/usr/sbin/e2fsck".to_string(),
                    "-f".to_string(),
                    "-y".to_string(),
                    device,
                ],
                timeout_seconds: 600,
                needs_confirmation: false,
            })
        }
        DiskOperationInput::FilesystemResize {
            device,
            fs,
            new_size_bytes,
            stage,
        } => build_filesystem_resize(device, fs, new_size_bytes, stage),
        DiskOperationInput::MountFilesystem {
            device,
            mountpoint,
            options,
            bind,
        } => {
            let device = if bind {
                safe_absolute_path(&device, "mount source")?
            } else {
                required_device(&device, "filesystem device")?
            };
            let mountpoint = safe_mountpoint(&mountpoint)?;
            let options = safe_mount_options(&options)?;
            let mut argv = vec!["/usr/sbin/mount".to_string()];
            if bind {
                argv.push("--bind".to_string());
            } else if !options.is_empty() {
                argv.extend(["-o".to_string(), options.join(",")]);
            }
            argv.extend([device, mountpoint]);
            Ok(DiskPlan {
                argv,
                timeout_seconds: 30,
                needs_confirmation: false,
            })
        }
        DiskOperationInput::UnmountFilesystem {
            mountpoint,
            recursive,
            lazy,
        } => {
            let mountpoint = safe_mountpoint(&mountpoint)?;
            let mut argv = vec!["/usr/sbin/umount".to_string()];
            if recursive {
                argv.push("-R".to_string());
            }
            if lazy {
                argv.push("-l".to_string());
            }
            argv.push(mountpoint);
            Ok(DiskPlan {
                argv,
                timeout_seconds: 30,
                needs_confirmation: false,
            })
        }
        DiskOperationInput::SetPartitionFlag {
            disk,
            part_num,
            flag,
            enabled,
            expected_partuuid,
        } => {
            assert_partition_identity(&disk, part_num, &expected_partuuid)?;
            build_set_partition_flag(disk, part_num, flag, enabled)
        }
        DiskOperationInput::FormatFilesystem {
            device,
            fs,
            label,
            expected_disk,
        } => build_mkfs(device, fs, label, expected_disk),
        DiskOperationInput::BtrfsSubvolumeCreate { mountpoint, name } => {
            let mountpoint = safe_mountpoint(&mountpoint)?;
            let name = safe_btrfs_subvolume_name(&name)?;
            Ok(DiskPlan {
                argv: vec![
                    "/usr/sbin/btrfs".to_string(),
                    "subvolume".to_string(),
                    "create".to_string(),
                    format!("{mountpoint}/{name}"),
                ],
                timeout_seconds: 60,
                needs_confirmation: false,
            })
        }
        DiskOperationInput::BtrfsSubvolumeSetDefault { mountpoint, name } => {
            let mountpoint = safe_mountpoint(&mountpoint)?;
            let name = safe_btrfs_subvolume_name(&name)?;
            Ok(DiskPlan {
                argv: vec![
                    "/usr/sbin/btrfs".to_string(),
                    "subvolume".to_string(),
                    "set-default".to_string(),
                    format!("{mountpoint}/{name}"),
                ],
                timeout_seconds: 60,
                needs_confirmation: false,
            })
        }
        DiskOperationInput::EnsureDirectory { path } => Ok(DiskPlan {
            argv: vec![
                "/usr/bin/mkdir".to_string(),
                "-p".to_string(),
                safe_absolute_path(&path, "directory path")?,
            ],
            timeout_seconds: 30,
            needs_confirmation: false,
        }),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn device() -> String {
        "/dev/sda".to_string()
    }

    #[test]
    fn projects_fixed_partition_commands() {
        let plan = build_plan(DiskOperationInput::CreatePartition {
            disk: device(),
            start: 1024 * 1024,
            size: 1024 * 1024 * 1024,
            fs: "btrfs".into(),
            label: "KythOS".into(),
            sector_size: 512,
        })
        .expect("partition plan should validate");
        assert_eq!(
            plan.argv,
            [
                "/usr/sbin/parted",
                "-s",
                "/dev/sda",
                "unit",
                "B",
                "mkpart",
                "KythOS",
                "btrfs",
                "1048576B",
                "1074789888B",
            ]
        );
    }

    #[test]
    fn projects_filesystem_commands_with_type_specific_labels() {
        // The pure argv builder still projects the exact mkfs command.
        let plan = build_mkfs_plan(device(), "fat32".into(), "EFI".into())
            .expect("filesystem plan should validate");
        assert_eq!(
            plan.argv,
            ["/usr/sbin/mkfs.fat", "-F32", "-n", "EFI", "/dev/sda"]
        );

        // The guarded entry point re-probes before building argv: /dev/sda
        // is a whole disk, never a validated replace target, so planning a
        // format for it fails closed instead of projecting mkfs argv.
        let error = build_plan(DiskOperationInput::FormatFilesystem {
            device: device(),
            fs: "fat32".into(),
            label: "EFI".into(),
            expected_disk: device(),
        })
        .expect_err("unvalidated format target must fail closed");
        assert!(
            error.contains("known disk") || error.contains("not present"),
            "{error}"
        );
    }

    #[test]
    fn projects_table_and_flag_operations() {
        let label = build_plan(DiskOperationInput::CreateLabel {
            disk: device(),
            table_type: "GPT".into(),
        })
        .expect("label plan should validate");
        assert_eq!(
            label.argv,
            ["/usr/sbin/parted", "-s", "/dev/sda", "mklabel", "gpt"]
        );

        let bios = build_plan(DiskOperationInput::CreateUnformattedPartition {
            disk: device(),
            start: 1024 * 1024,
            size: 1024 * 1024,
            label: "biosboot".into(),
            sector_size: 512,
        })
        .expect("unformatted partition plan should validate");
        assert_eq!(
            bios.argv,
            [
                "/usr/sbin/parted",
                "-s",
                "/dev/sda",
                "unit",
                "B",
                "mkpart",
                "biosboot",
                "1048576B",
                "2096640B",
            ]
        );

        let delete = build_delete_partition(device(), 2).expect("delete plan should validate");
        assert_eq!(
            delete.argv,
            ["/usr/sbin/parted", "-s", "/dev/sda", "rm", "2"]
        );

        let flag = build_set_partition_flag(device(), 1, "esp".into(), false)
            .expect("flag plan should validate");
        assert_eq!(
            flag.argv,
            [
                "/usr/sbin/parted",
                "-s",
                "/dev/sda",
                "set",
                "1",
                "esp",
                "off"
            ]
        );
    }

    #[test]
    fn projects_backup_and_restore_operations() {
        // GPT tables keep the sgdisk backup format.
        let backup = table_backup_plan(device(), "/tmp/table.backup".into(), "gpt", None)
            .expect("backup plan should validate");
        assert_eq!(
            backup.argv,
            [
                "/usr/sbin/sgdisk",
                "--backup",
                "/tmp/table.backup",
                "/dev/sda"
            ]
        );

        let restore = table_restore_plan(device(), "/tmp/table.backup".into(), "gpt", None)
            .expect("restore plan should validate");
        assert_eq!(
            restore.argv,
            [
                "/usr/sbin/sgdisk",
                "--load-backup",
                "/tmp/table.backup",
                "/dev/sda",
            ]
        );

        // MBR ("dos") tables use sfdisk: sgdisk cannot read or write them.
        // sfdisk dumps to stdout, so the plan shells the redirection; the
        // interpolated paths pass strict validators with no shell
        // metacharacters.
        let dos_backup = table_backup_plan(
            device(),
            "/tmp/table.backup".into(),
            "dos",
            Some("/usr/sbin/sfdisk"),
        )
        .expect("MBR backup plan should validate");
        assert_eq!(
            dos_backup.argv,
            [
                "/bin/sh",
                "-c",
                "exec /usr/sbin/sfdisk --dump \"$1\" > \"$2\"",
                "kyth-sfdisk-dump",
                "/dev/sda",
                "/tmp/table.backup",
            ]
        );

        let dos_restore = table_restore_plan(
            device(),
            "/tmp/table.backup".into(),
            "dos",
            Some("/usr/sbin/sfdisk"),
        )
        .expect("MBR restore plan should validate");
        assert_eq!(
            dos_restore.argv,
            [
                "/bin/sh",
                "-c",
                "exec /usr/sbin/sfdisk --force \"$1\" < \"$2\"",
                "kyth-sfdisk-load",
                "/dev/sda",
                "/tmp/table.backup",
            ]
        );

        // MBR without sfdisk fails closed instead of running sgdisk against
        // a DOS table.
        let missing = table_backup_plan(device(), "/tmp/table.backup".into(), "dos", None)
            .expect_err("MBR backup without sfdisk must fail closed");
        assert!(missing.contains("sfdisk"), "{missing}");
        assert!(table_restore_plan(device(), "/tmp/table.backup".into(), "dos", None).is_err());
        assert!(table_backup_plan(device(), "/tmp/table.backup".into(), "bsd", None).is_err());
    }

    #[test]
    fn syncs_backup_file_and_parent_directory() {
        let directory = tempfile::tempdir().expect("temporary directory");
        let path = directory.path().join("table.backup");
        std::fs::write(&path, b"partition table").expect("backup file");
        sync_backup(path.to_str().expect("UTF-8 temporary path"))
            .expect("backup and directory should sync");
    }

    #[test]
    fn rejects_missing_backup_when_syncing() {
        let error = sync_backup("/tmp/kyth-missing-partition-backup")
            .expect_err("missing backup must fail closed");
        assert!(error.contains("open partition backup"));
    }

    #[test]
    fn projects_interactive_resize_with_fixed_confirmation() {
        let plan = build_resize_partition(device(), 3, 128 * 1024 * 1024, 64 * 1024 * 1024, 512)
            .expect("resize plan should validate");
        assert_eq!(
            plan.argv,
            [
                "/usr/sbin/parted",
                "---pretend-input-tty",
                "/dev/sda",
                "unit",
                "B",
                "resizepart",
                "3",
                "201326080B",
            ]
        );
        assert!(plan.needs_confirmation);
    }

    #[test]
    fn projects_filesystem_shrink_stages() {
        let check = build_plan(DiskOperationInput::FilesystemCheck { device: device() })
            .expect("filesystem check plan should validate");
        assert_eq!(check.argv, ["/usr/sbin/e2fsck", "-f", "-y", "/dev/sda"]);

        let ntfs = build_plan(DiskOperationInput::FilesystemResize {
            device: device(),
            fs: "ntfs".into(),
            new_size_bytes: 10 * 1024 * 1024,
            stage: "dry_run".into(),
        })
        .expect("NTFS dry-run plan should validate");
        assert_eq!(
            ntfs.argv,
            [
                "/usr/sbin/ntfsresize",
                "--no-action",
                "--size",
                "10485760",
                "/dev/sda",
            ]
        );
        assert!(!ntfs.needs_confirmation);

        let ext = build_plan(DiskOperationInput::FilesystemResize {
            device: device(),
            fs: "ext4".into(),
            new_size_bytes: 10 * 1024 + 1,
            stage: "resize".into(),
        })
        .expect("ext resize plan should validate");
        assert_eq!(ext.argv, ["/usr/sbin/resize2fs", "/dev/sda", "10K"]);

        let btrfs = build_plan(DiskOperationInput::FilesystemResize {
            device: device(),
            fs: "btrfs".into(),
            new_size_bytes: 20 * 1024 * 1024,
            stage: "resize".into(),
        })
        .expect("Btrfs resize plan should validate");
        assert_eq!(
            btrfs.argv,
            [
                "/usr/sbin/btrfs",
                "filesystem",
                "resize",
                "20971520",
                "/dev/sda",
            ]
        );
    }

    #[test]
    fn projects_btrfs_mount_lifecycle() {
        let mount = build_plan(DiskOperationInput::MountFilesystem {
            device: device(),
            mountpoint: "/tmp/kyth-resize".into(),
            options: vec![],
            bind: false,
        })
        .expect("mount plan should validate");
        assert_eq!(
            mount.argv,
            ["/usr/sbin/mount", "/dev/sda", "/tmp/kyth-resize"]
        );

        let subvolume = build_plan(DiskOperationInput::MountFilesystem {
            device: device(),
            mountpoint: "/tmp/kyth-target".into(),
            options: vec!["subvol=@".into(), "ro".into()],
            bind: false,
        })
        .expect("mount options should validate");
        assert_eq!(
            subvolume.argv,
            [
                "/usr/sbin/mount",
                "-o",
                "subvol=@,ro",
                "/dev/sda",
                "/tmp/kyth-target"
            ]
        );

        let bind = build_plan(DiskOperationInput::MountFilesystem {
            device: "/boot/efi".into(),
            mountpoint: "/tmp/kyth-target/boot/efi".into(),
            options: vec![],
            bind: true,
        })
        .expect("bind mount should validate");
        assert_eq!(
            bind.argv,
            [
                "/usr/sbin/mount",
                "--bind",
                "/boot/efi",
                "/tmp/kyth-target/boot/efi"
            ]
        );

        let unmount = build_plan(DiskOperationInput::UnmountFilesystem {
            mountpoint: "/tmp/kyth-resize".into(),
            recursive: false,
            lazy: false,
        })
        .expect("unmount plan should validate");
        assert_eq!(unmount.argv, ["/usr/sbin/umount", "/tmp/kyth-resize"]);

        let recursive = build_plan(DiskOperationInput::UnmountFilesystem {
            mountpoint: "/tmp/kyth-resize".into(),
            recursive: true,
            lazy: true,
        })
        .expect("recursive unmount should validate");
        assert_eq!(
            recursive.argv,
            ["/usr/sbin/umount", "-R", "-l", "/tmp/kyth-resize"]
        );
    }

    #[test]
    fn rejects_unsafe_paths_and_values() {
        let cases = [
            DiskOperationInput::CreateLabel {
                disk: "../../etc".into(),
                table_type: "gpt".into(),
            },
            DiskOperationInput::BackupTable {
                disk: device(),
                backup_path: "/tmp/../etc/x".into(),
            },
            DiskOperationInput::CreateLabel {
                disk: device(),
                table_type: "bsd".into(),
            },
            DiskOperationInput::SetPartitionFlag {
                disk: device(),
                part_num: 1,
                flag: "boot".into(),
                enabled: true,
                expected_partuuid: "9a3b4c5d-6e7f-8a9b-0c1d-2e3f4a5b6c7d".into(),
            },
            DiskOperationInput::FormatFilesystem {
                device: device(),
                fs: "zfs".into(),
                label: String::new(),
                expected_disk: device(),
            },
        ];
        for input in cases {
            assert!(build_plan(input).is_err());
        }
        assert!(build_plan(DiskOperationInput::BtrfsSubvolumeCreate {
            mountpoint: "/tmp/kyth-btrfs-root".into(),
            name: "../escape".into(),
        })
        .is_err());
    }

    #[test]
    fn projects_fixed_btrfs_subvolume_operations() {
        let create = build_plan(DiskOperationInput::BtrfsSubvolumeCreate {
            mountpoint: "/run/kyth-installer/btrfs-root".into(),
            name: "@home".into(),
        })
        .expect("subvolume create should validate");
        assert_eq!(
            create.argv,
            [
                "/usr/sbin/btrfs",
                "subvolume",
                "create",
                "/run/kyth-installer/btrfs-root/@home"
            ]
        );

        let default = build_plan(DiskOperationInput::BtrfsSubvolumeSetDefault {
            mountpoint: "/run/kyth-installer/btrfs-root".into(),
            name: "@".into(),
        })
        .expect("subvolume default should validate");
        assert_eq!(
            default.argv,
            [
                "/usr/sbin/btrfs",
                "subvolume",
                "set-default",
                "/run/kyth-installer/btrfs-root/@"
            ]
        );

        let directory = build_plan(DiskOperationInput::EnsureDirectory {
            path: "/run/kyth-installer/alongside-target/boot/efi".into(),
        })
        .expect("directory creation should validate");
        assert_eq!(
            directory.argv,
            [
                "/usr/bin/mkdir",
                "-p",
                "/run/kyth-installer/alongside-target/boot/efi"
            ]
        );
    }

    #[test]
    fn partition_identity_is_asserted_before_acting() {
        // An empty or malformed expected PARTUUID fails closed before any
        // probe runs: there is no identity to assert.
        for input in [
            DiskOperationInput::DeletePartition {
                disk: device(),
                part_num: 2,
                expected_partuuid: String::new(),
            },
            DiskOperationInput::SetPartitionFlag {
                disk: device(),
                part_num: 1,
                flag: "esp".into(),
                enabled: true,
                expected_partuuid: "not-a-uuid!!".into(),
            },
            DiskOperationInput::ResizePartition {
                disk: device(),
                part_num: 3,
                start: 128 * 1024 * 1024,
                new_size: 64 * 1024 * 1024,
                sector_size: 512,
                expected_partuuid: String::new(),
            },
        ] {
            let error = build_plan(input).expect_err("missing identity must fail closed");
            assert!(error.contains("partition UUID"), "{error}");
        }
        // A well-formed PARTUUID that the fresh probe cannot confirm fails
        // closed too, whether the disk is absent or the number now points
        // at a different partition.
        assert!(build_plan(DiskOperationInput::DeletePartition {
            disk: device(),
            part_num: 2,
            expected_partuuid: "9a3b4c5d-6e7f-8a9b-0c1d-2e3f4a5b6c7d".into(),
        })
        .is_err());

        // The pure builders keep their own input validation.
        assert!(build_delete_partition(device(), 0).is_err());
        assert!(build_resize_partition(device(), 0, 1024 * 1024, 1024 * 1024, 512).is_err());
        assert!(build_set_partition_flag(device(), 1, "boot".into(), true).is_err());
    }

    #[test]
    fn rejects_geometry_overflow_and_bad_sector_sizes() {
        for (start, size, sector_size) in [
            (u64::MAX, 512, 512),
            (1024, 511, 512),
            (1024, 1024, 1000),
            (1025, 1024, 512),
            // Sector-aligned but not 1 MiB aligned.
            (2048, 1024 * 1024, 512),
        ] {
            let input = DiskOperationInput::CreateUnformattedPartition {
                disk: device(),
                start,
                size,
                label: "biosboot".into(),
                sector_size,
            };
            assert!(build_plan(input).is_err());
        }
    }
}
