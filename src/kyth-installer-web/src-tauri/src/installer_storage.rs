//! Read-only `lsblk --json --bytes` snapshot parsing for installer discovery.
//!
//! The parser accepts explicit snapshots so the safety policy is testable
//! without touching devices. The root-owned daemon supplies those snapshots
//! through fixed, read-only probes and serializes the API records directly.

use serde::{Deserialize, Serialize};

const EFI_PART_GUID: &str = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b";
const MIN_KYTHOS_BYTES: u64 = 32 * 1024 * 1024 * 1024;
const NTFS_MIN_BYTES: u64 = (64 + 32) * 1024 * 1024 * 1024;
const BIOS_BOOT_GUID: &str = "21686148-6449-6e6f-744e-656564454649";
const GPT_RESERVE_BYTES: u64 = 1024 * 1024;

#[derive(Debug, Deserialize)]
struct LsblkSnapshot {
    #[serde(default)]
    blockdevices: Vec<LsblkDevice>,
}

#[derive(Debug, Deserialize)]
struct LsblkDevice {
    name: Option<String>,
    partn: Option<u32>,
    size: Option<u64>,
    #[serde(rename = "type")]
    device_type: Option<String>,
    pkname: Option<String>,
    fstype: Option<String>,
    parttype: Option<String>,
    label: Option<String>,
    model: Option<String>,
    mountpoint: Option<String>,
    mountpoints: Option<Vec<Option<String>>>,
    start: Option<u64>,
    ro: Option<bool>,
    rm: Option<bool>,
    rota: Option<bool>,
    tran: Option<String>,
    pttype: Option<String>,
    #[serde(default)]
    children: Vec<LsblkDevice>,
}

#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
pub(crate) struct DiskRecord {
    pub name: String,
    pub size_bytes: u64,
    pub model: String,
    pub ssd: bool,
    pub transport: String,
    pub removable: bool,
    pub partition_table: String,
    pub current: bool,
}

#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
pub(crate) struct PartitionRecord {
    pub name: String,
    pub size_bytes: u64,
    pub start_bytes: u64,
    pub fstype: String,
    pub label: String,
    pub parttype: String,
    pub mountpoints: Vec<String>,
    pub efi: bool,
    pub current: bool,
    pub in_use: bool,
    pub read_only: bool,
    pub alongside_candidate: bool,
    pub ntfs_resize_candidate: bool,
}

#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
pub(crate) struct FreeRegionRecord {
    pub start_bytes: u64,
    pub end_bytes: u64,
    pub size_bytes: u64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct PartitionProbe {
    pub name: String,
    pub number: u32,
    pub size_bytes: u64,
    pub start_bytes: u64,
    pub fstype: String,
    pub label: String,
    pub efi: bool,
    pub current: bool,
    pub in_use: bool,
    pub read_only: bool,
}

/// Filesystems that always signal somebody else's data. The alongside and
/// manual paths run `mkfs.btrfs -f` on the target, so accepting one of these
/// would destroy a Windows/macOS/data volume outright. Mirrors Python's
/// `_UNSAFE_ALONGSIDE_FSTYPES` (`plan_validate.py`).
const FOREIGN_DATA_FSTYPES: &[&str] = &[
    "ntfs",
    "ntfs3",
    "bitlocker",
    "apfs",
    "hfsplus",
    "hfs",
    "exfat",
];

/// Why a partition must not be formatted as the KythOS target, if it looks
/// like it holds someone's data. `fstype` must already be lowercased.
fn foreign_data_reason(fstype: &str, label: &str, role: &str) -> Option<String> {
    let label = label.trim();
    let labeled = if label.is_empty() {
        String::new()
    } else {
        format!(" labeled {label:?}")
    };
    if FOREIGN_DATA_FSTYPES.contains(&fstype) {
        return Some(format!(
            "The selected {role} holds a {fstype} filesystem{labeled} and installing there \
would destroy its contents. Back up its data, or choose an empty partition, unallocated \
space, or the Windows-shrink option."
        ));
    }
    if !fstype.is_empty() && fstype != "btrfs" && !label.is_empty() {
        return Some(format!(
            "The selected {role} is a labeled {fstype} volume ({label:?}) that appears to hold \
data, and installing there would format it. Back up its contents, clear the partition \
first, or choose a different target."
        ));
    }
    None
}

/// Re-validate the alongside/manual target against a fresh snapshot
/// immediately before it is formatted. Mirrors Python's
/// `_validate_partition_target` plus its parent-disk check: the partition
/// must be on the selected disk, must not be the ESP, must be unmounted,
/// unstacked, writable, large enough, and must not look like it holds data.
pub(crate) fn validate_replace_target(
    input: &str,
    disk: &str,
    partition: &str,
    role: &str,
) -> Result<PartitionProbe, String> {
    let probe = partition_probe_from_snapshot(input, disk, partition)?;
    if probe.efi {
        return Err(format!(
            "The EFI system partition cannot be used as the KythOS {role}."
        ));
    }
    if probe.current || probe.in_use || probe.read_only {
        return Err(format!(
            "The selected {role} is mounted, read-only, or has active encrypted/LVM mappings."
        ));
    }
    if probe.size_bytes < MIN_KYTHOS_BYTES {
        return Err(format!(
            "The {role} is too small. At least {} GiB is required.",
            MIN_KYTHOS_BYTES / (1024 * 1024 * 1024)
        ));
    }
    if let Some(reason) = foreign_data_reason(&probe.fstype, &probe.label, role) {
        return Err(reason);
    }
    Ok(probe)
}

/// The ESP selected from a fresh snapshot, including a safe live-session
/// mountpoint when one is already available for bind mounting.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct EfiPartition {
    pub name: String,
    pub mounted_at: Option<String>,
}

fn normalize_device_path(raw: &str) -> Option<String> {
    let value = raw.trim();
    if value.is_empty() {
        return None;
    }
    let value = if value.starts_with("/dev/") {
        value.to_string()
    } else {
        format!("/dev/{value}")
    };
    if !value.starts_with("/dev/")
        || value.contains("..")
        || !value.bytes().all(|byte| {
            byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'/' | b'+' | b':' | b'-')
        })
    {
        return None;
    }
    Some(value)
}

fn mountpoints(device: &LsblkDevice) -> Vec<String> {
    if let Some(values) = &device.mountpoints {
        return values.iter().filter_map(|value| value.clone()).collect();
    }
    device.mountpoint.clone().into_iter().collect()
}

fn descendant_mountpoints(device: &LsblkDevice) -> Vec<String> {
    device
        .children
        .iter()
        .flat_map(|child| {
            let mut mounts = mountpoints(child);
            mounts.extend(descendant_mountpoints(child));
            mounts
        })
        .collect()
}

fn parse_snapshot(input: &str) -> Result<LsblkSnapshot, String> {
    serde_json::from_str(input).map_err(|error| format!("invalid lsblk snapshot: {error}"))
}

fn device_ancestry(
    input: &str,
) -> Result<std::collections::HashMap<String, (String, Option<String>)>, String> {
    let snapshot = parse_snapshot(input)?;
    let mut devices = std::collections::HashMap::new();
    fn walk(
        entries: &[LsblkDevice],
        devices: &mut std::collections::HashMap<String, (String, Option<String>)>,
    ) {
        for entry in entries {
            if let Some(name) = entry.name.as_deref().and_then(normalize_device_path) {
                let parent = entry.pkname.as_deref().and_then(normalize_device_path);
                let _ = devices.insert(
                    name,
                    (entry.device_type.clone().unwrap_or_default(), parent),
                );
            }
            walk(&entry.children, devices);
        }
    }
    walk(&snapshot.blockdevices, &mut devices);
    Ok(devices)
}

/// Resolve a mount source to its physical disk using an ancestry snapshot.
pub(crate) fn parent_disk_in_snapshot(input: &str, source: &str) -> Result<Option<String>, String> {
    let devices = device_ancestry(input)?;
    let mut current = normalize_device_path(source);
    let mut seen = std::collections::HashSet::new();
    while let Some(device) = current {
        if !seen.insert(device.clone()) {
            return Ok(None);
        }
        let Some((device_type, parent)) = devices.get(&device) else {
            return Ok(None);
        };
        if device_type == "disk" {
            return Ok(Some(device));
        }
        current = parent.clone();
    }
    Ok(None)
}

/// Build the runtime disk inventory from separate device and ancestry probes.
pub(crate) fn runtime_disks_from_snapshots(
    disk_snapshot: &str,
    ancestry_snapshot: &str,
    protected_sources: &[String],
    current_source: Option<&str>,
) -> Result<Vec<DiskRecord>, String> {
    let mut protected = std::collections::HashSet::new();
    for source in protected_sources {
        if let Some(disk) = parent_disk_in_snapshot(ancestry_snapshot, source)? {
            protected.insert(disk);
        }
    }
    let current_disk = current_source
        .map(|source| parent_disk_in_snapshot(ancestry_snapshot, source))
        .transpose()?
        .flatten();
    parse_disks(
        disk_snapshot,
        &protected.into_iter().collect::<Vec<_>>(),
        current_disk.as_deref(),
    )
}

fn disk_metadata(input: &str, disk: &str) -> Result<(u64, bool), String> {
    let snapshot = parse_snapshot(input)?;
    let target = normalize_device_path(disk)
        .ok_or_else(|| "invalid disk path for storage query".to_string())?;
    snapshot
        .blockdevices
        .iter()
        .find_map(|entry| {
            let name = entry.name.as_deref().and_then(normalize_device_path)?;
            (name == target && entry.device_type.as_deref() == Some("disk")).then(|| {
                (
                    entry.size.unwrap_or(0),
                    entry
                        .pttype
                        .as_deref()
                        .unwrap_or_default()
                        .eq_ignore_ascii_case("gpt"),
                )
            })
        })
        .ok_or_else(|| "storage query did not return the selected disk".to_string())
}

/// Calculate free regions using the same reserved-boundary and BIOS-boot
/// minimums as the Python compatibility query.
pub(crate) fn free_regions(
    disk_snapshot: &str,
    disk: &str,
    sector_size: u64,
) -> Result<Vec<FreeRegionRecord>, String> {
    if !sector_size.is_power_of_two() || !(512..=4096).contains(&sector_size) {
        return Err("storage query returned an unsupported sector size".to_string());
    }
    let (disk_size, is_gpt) = disk_metadata(disk_snapshot, disk)?;
    if disk_size <= GPT_RESERVE_BYTES.saturating_mul(2) {
        return Ok(Vec::new());
    }
    let partitions = parse_partitions(disk_snapshot)?;
    let has_bios_boot = partitions
        .iter()
        .any(|part| part.parttype.eq_ignore_ascii_case(BIOS_BOOT_GUID));
    let required = MIN_KYTHOS_BYTES
        + if is_gpt && !has_bios_boot {
            GPT_RESERVE_BYTES
        } else {
            0
        };
    let mut spans = Vec::new();
    for partition in partitions {
        if partition.size_bytes == 0
            || partition.start_bytes > disk_size
            || partition.size_bytes > disk_size.saturating_sub(partition.start_bytes)
        {
            return Ok(Vec::new());
        }
        let start = (partition.start_bytes / sector_size) * sector_size;
        let size = (partition.size_bytes / sector_size) * sector_size;
        if size == 0 || start > disk_size.saturating_sub(size) {
            return Ok(Vec::new());
        }
        spans.push((start, start + size));
    }
    spans.sort_unstable();
    let usable_end = disk_size - GPT_RESERVE_BYTES;
    let mut cursor = GPT_RESERVE_BYTES;
    let mut regions = Vec::new();
    for (start, end) in spans {
        if start > cursor {
            append_region(&mut regions, cursor, start, sector_size, required);
        }
        cursor = cursor.max(end);
    }
    if cursor < usable_end {
        append_region(&mut regions, cursor, usable_end, sector_size, required);
    }
    Ok(regions)
}

fn append_region(
    regions: &mut Vec<FreeRegionRecord>,
    start: u64,
    end: u64,
    sector_size: u64,
    required: u64,
) {
    let aligned_start = start.div_ceil(sector_size) * sector_size;
    let aligned_end = (end / sector_size) * sector_size;
    if aligned_end > aligned_start && aligned_end - aligned_start >= required {
        regions.push(FreeRegionRecord {
            start_bytes: aligned_start,
            end_bytes: aligned_end,
            size_bytes: aligned_end - aligned_start,
        });
    }
}

/// Parse safe, writable whole-disk records from an explicit lsblk snapshot.
///
pub(crate) fn parse_disks(
    input: &str,
    protected: &[String],
    current_disk: Option<&str>,
) -> Result<Vec<DiskRecord>, String> {
    let snapshot = parse_snapshot(input)?;
    Ok(snapshot
        .blockdevices
        .iter()
        .filter(|device| device.device_type.as_deref() == Some("disk"))
        .filter_map(|device| {
            let name = normalize_device_path(device.name.as_deref()?)?;
            let size_bytes = device.size.unwrap_or(0);
            if size_bytes == 0 || device.ro.unwrap_or(false) || protected.contains(&name) {
                return None;
            }
            Some(DiskRecord {
                current: current_disk == Some(name.as_str()),
                name,
                size_bytes,
                model: device
                    .model
                    .as_deref()
                    .unwrap_or("Unknown drive")
                    .trim()
                    .to_string(),
                ssd: !device.rota.unwrap_or(false),
                transport: device.tran.clone().unwrap_or_default(),
                removable: device.rm.unwrap_or(false),
                partition_table: device
                    .pttype
                    .clone()
                    .unwrap_or_default()
                    .to_ascii_lowercase(),
            })
        })
        .collect())
}

/// Parse partition records, including descendant mounts, from an lsblk tree.
///
pub(crate) fn parse_partitions(input: &str) -> Result<Vec<PartitionRecord>, String> {
    let snapshot = parse_snapshot(input)?;
    let mut partitions = Vec::new();

    fn walk(devices: &[LsblkDevice], partitions: &mut Vec<PartitionRecord>) {
        for device in devices {
            if device.device_type.as_deref() == Some("part") {
                if let Some(name) = device.name.as_deref().and_then(normalize_device_path) {
                    let size_bytes = device.size.unwrap_or(0);
                    let fstype = device
                        .fstype
                        .as_deref()
                        .unwrap_or_default()
                        .to_ascii_lowercase();
                    let parttype = device
                        .parttype
                        .as_deref()
                        .unwrap_or_default()
                        .to_ascii_lowercase();
                    let mut mounts = mountpoints(device);
                    mounts.extend(descendant_mountpoints(device));
                    let efi = parttype == EFI_PART_GUID
                        || (fstype == "vfat" && mounts.iter().any(|mount| mount == "/boot/efi"));
                    let current = !mounts.is_empty();
                    let in_use = !device.children.is_empty();
                    let read_only = device.ro.unwrap_or(false);
                    // Replace-flow eligibility: big enough, not the ESP, not
                    // mounted, with no stacked device on top, and writable.
                    // Windows filesystems are never replace candidates — the
                    // resize flow owns NTFS via ntfs_resize_candidate below,
                    // so "Replace a partition" cannot silently offer a
                    // Windows partition for destruction.
                    let replaceable =
                        size_bytes >= MIN_KYTHOS_BYTES && !efi && !current && !in_use && !read_only;
                    let is_windows = matches!(fstype.as_str(), "ntfs" | "ntfs3");
                    let label = device.label.clone().unwrap_or_default();
                    // Same content gate the commit path enforces, so the UI
                    // never offers a partition the format step will refuse.
                    let alongside_candidate =
                        replaceable && foreign_data_reason(&fstype, &label, "").is_none();
                    let ntfs_resize_candidate =
                        replaceable && is_windows && size_bytes >= NTFS_MIN_BYTES;
                    partitions.push(PartitionRecord {
                        name,
                        size_bytes,
                        start_bytes: device.start.unwrap_or(0).saturating_mul(512),
                        fstype,
                        label,
                        parttype,
                        mountpoints: mounts,
                        efi,
                        current,
                        in_use,
                        read_only,
                        alongside_candidate,
                        ntfs_resize_candidate,
                    });
                }
            }
            walk(&device.children, partitions);
        }
    }

    walk(&snapshot.blockdevices, &mut partitions);
    Ok(partitions)
}

/// Select the installed Btrfs root partition from a fresh lsblk tree.
///
/// Partition numbers are not guessed: the result must be a child of the
/// requested disk, must be a partition, and must report Btrfs as its
/// filesystem. EFI, BIOS-boot, and unrelated filesystems are ignored.
pub(crate) fn root_partition_from_snapshot(input: &str, disk: &str) -> Result<String, String> {
    let disk = normalize_device_path(disk)
        .ok_or_else(|| "root partition query has an invalid disk".to_string())?;
    let snapshot = parse_snapshot(input)?;
    let root = snapshot
        .blockdevices
        .iter()
        .find(|device| {
            normalize_device_path(device.name.as_deref().unwrap_or_default()).as_deref()
                == Some(disk.as_str())
                && device.device_type.as_deref() == Some("disk")
        })
        .ok_or_else(|| "target disk was not present in root partition probe".to_string())?;
    let mut candidates = Vec::new();
    fn collect(device: &LsblkDevice, candidates: &mut Vec<String>) {
        if device.device_type.as_deref() == Some("part")
            && device
                .fstype
                .as_deref()
                .map(str::to_ascii_lowercase)
                .as_deref()
                == Some("btrfs")
        {
            if let Some(name) = device.name.as_deref().and_then(normalize_device_path) {
                candidates.push(name);
            }
        }
        for child in &device.children {
            collect(child, candidates);
        }
    }
    collect(root, &mut candidates);
    candidates.into_iter().next().ok_or_else(|| {
        "target disk has no Btrfs root partition after bootc installation".to_string()
    })
}

/// Find the EFI System Partition on the selected disk without trusting a
/// caller-supplied partition number. The snapshot is expected to come from
/// `lsblk ... <disk>`, but the name prefix check also keeps an accidentally
/// broad snapshot from selecting another disk's ESP.
pub(crate) fn efi_partition_from_snapshot(
    input: &str,
    disk: &str,
) -> Result<Option<EfiPartition>, String> {
    let disk = normalize_device_path(disk)
        .ok_or_else(|| "EFI partition query has an invalid disk".to_string())?;
    let mut candidates = parse_partitions(input)?
        .into_iter()
        .filter(|part| {
            part.efi
                && part.name.strip_prefix(&disk).is_some_and(|suffix| {
                    suffix
                        .strip_prefix('p')
                        .unwrap_or(suffix)
                        .bytes()
                        .all(|byte| byte.is_ascii_digit())
                        && !suffix.is_empty()
                })
        })
        .map(|part| EfiPartition {
            name: part.name,
            mounted_at: part.mountpoints.into_iter().find(|mount| {
                mount.starts_with('/') && !mount.contains("..") && !mount.contains("//")
            }),
        });
    Ok(candidates.next())
}

/// Revalidate one partition as a member of the selected disk.
///
/// The returned geometry is intentionally sourced from the same fresh tree
/// used to validate the parent relationship. Callers must use it immediately
/// before a destructive operation; a stale caller-supplied partition number or
/// size is never trusted.
pub(crate) fn partition_probe_from_snapshot(
    input: &str,
    disk: &str,
    partition: &str,
) -> Result<PartitionProbe, String> {
    let disk = normalize_device_path(disk)
        .ok_or_else(|| "partition query has an invalid disk".to_string())?;
    let partition = normalize_device_path(partition)
        .ok_or_else(|| "partition query has an invalid partition".to_string())?;
    let snapshot = parse_snapshot(input)?;
    let root = snapshot
        .blockdevices
        .iter()
        .find(|device| {
            normalize_device_path(device.name.as_deref().unwrap_or_default()).as_deref()
                == Some(disk.as_str())
                && device.device_type.as_deref() == Some("disk")
        })
        .ok_or_else(|| "target disk was not present in partition probe".to_string())?;

    fn find_partition(device: &LsblkDevice, wanted: &str) -> Option<PartitionProbe> {
        if device.device_type.as_deref() == Some("part")
            && normalize_device_path(device.name.as_deref().unwrap_or_default()).as_deref()
                == Some(wanted)
        {
            let name = device.name.as_deref().and_then(normalize_device_path)?;
            let number = device.partn?;
            let fstype = device
                .fstype
                .as_deref()
                .unwrap_or_default()
                .to_ascii_lowercase();
            let mounts = mountpoints(device);
            let efi = device
                .parttype
                .as_deref()
                .is_some_and(|parttype| parttype.eq_ignore_ascii_case(EFI_PART_GUID))
                || (fstype == "vfat" && mounts.iter().any(|mount| mount == "/boot/efi"));
            return Some(PartitionProbe {
                name,
                number,
                size_bytes: device.size.unwrap_or(0),
                start_bytes: device.start.unwrap_or(0).saturating_mul(512),
                fstype,
                label: device.label.clone().unwrap_or_default(),
                efi,
                current: !mounts.is_empty(),
                in_use: !device.children.is_empty(),
                read_only: device.ro.unwrap_or(false),
            });
        }
        device
            .children
            .iter()
            .find_map(|child| find_partition(child, wanted))
    }

    find_partition(root, &partition)
        .ok_or_else(|| "selected partition was not present on the target disk".to_string())
}

/// Confirm that a selected free-space interval is still one of the safe
/// regions in a fresh disk snapshot.
pub(crate) fn contains_free_region(
    input: &str,
    disk: &str,
    start: u64,
    end: u64,
    sector_size: u64,
) -> Result<bool, String> {
    if end <= start {
        return Ok(false);
    }
    Ok(free_regions(input, disk, sector_size)?
        .iter()
        .any(|region| start >= region.start_bytes && end <= region.end_bytes))
}

/// Identify one newly created partition by its post-mutation geometry.
///
/// A name-set difference alone is unsafe when udev exposes stale entries or a
/// partition operation creates more than one object. Geometry must match
/// within one MiB and exactly one new candidate must remain.
pub(crate) fn new_partition_from_snapshots(
    before: &str,
    after: &str,
    start_bytes: u64,
    size_bytes: u64,
) -> Result<String, String> {
    if start_bytes == 0 || size_bytes == 0 {
        return Err("new partition geometry must be positive".to_string());
    }
    let prior = parse_partitions(before)?
        .into_iter()
        .map(|partition| partition.name)
        .collect::<std::collections::HashSet<_>>();
    const GEOMETRY_TOLERANCE: u64 = 1024 * 1024;
    let candidates = parse_partitions(after)?
        .into_iter()
        .filter(|partition| !prior.contains(&partition.name))
        .filter(|partition| {
            partition.start_bytes.abs_diff(start_bytes) <= GEOMETRY_TOLERANCE
                && partition.size_bytes.abs_diff(size_bytes) <= GEOMETRY_TOLERANCE
        })
        .map(|partition| partition.name)
        .collect::<Vec<_>>();
    match candidates.as_slice() {
        [name] => Ok(name.clone()),
        [] => Err("new partition was not visible at the requested geometry".to_string()),
        _ => Err("multiple new partitions matched the requested geometry".to_string()),
    }
}

pub(crate) fn has_bios_boot_partition(input: &str) -> Result<bool, String> {
    Ok(parse_partitions(input)?
        .into_iter()
        .any(|partition| partition.parttype.eq_ignore_ascii_case(BIOS_BOOT_GUID)))
}

/// Refuse an alongside install that a legacy-BIOS boot could not start.
/// GRUB on a GPT disk booted from legacy BIOS needs a BIOS boot partition;
/// without one it falls back to blocklists, which Btrfs rejects. Alongside
/// reuses an existing partition and never creates one (free-space and
/// NTFS-shrink installs do), so it must fail before formatting anything.
/// UEFI boots use the ESP and are unaffected. Mirrors Python's
/// `_needs_bios_boot` refusal in `plan_validate.py`.
pub(crate) fn validate_alongside_bios_boot(
    input: &str,
    disk: &str,
    uefi_boot: bool,
) -> Result<(), String> {
    if uefi_boot {
        return Ok(());
    }
    let (_, is_gpt) = disk_metadata(input, disk)?;
    if !is_gpt {
        return Ok(());
    }
    let disk = normalize_device_path(disk)
        .ok_or_else(|| "BIOS boot query has an invalid disk".to_string())?;
    let has_bios_boot = parse_partitions(input)?.iter().any(|partition| {
        on_selected_disk(&partition.name, &disk)
            && partition.parttype.eq_ignore_ascii_case(BIOS_BOOT_GUID)
    });
    if has_bios_boot {
        return Ok(());
    }
    Err(
        "Legacy BIOS on GPT requires a 1 MiB BIOS boot partition for GRUB. Create a 1 MiB \
partition with the bios_grub flag in the manual partition editor, or use free-space/NTFS-shrink \
install which creates it automatically. Without it GRUB falls back to blocklists, which Btrfs \
rejects."
            .to_string(),
    )
}

/// Microsoft basic-data GUID: the Windows-indicator partition type.
const WINDOWS_DATA_GUID: &str = "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7";

/// ESP-preservation / Windows-indicator / BitLocker state for one target
/// disk, derived from the same lsblk snapshot the Python compatibility path
/// (`list_partitions`) reads. One detection source, two consumers.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct StoragePreflight {
    pub disk: String,
    pub esp_present: bool,
    pub esp_name: String,
    pub windows_present: bool,
    pub bitlocker_locked: bool,
    pub checked_partitions: usize,
}

fn on_selected_disk(name: &str, disk: &str) -> bool {
    name.strip_prefix(disk).is_some_and(|suffix| {
        !suffix.is_empty()
            && suffix
                .strip_prefix('p')
                .unwrap_or(suffix)
                .bytes()
                .all(|byte| byte.is_ascii_digit())
    })
}

pub(crate) fn storage_preflight_from_snapshot(
    input: &str,
    disk: &str,
) -> Result<StoragePreflight, String> {
    let disk = normalize_device_path(disk)
        .ok_or_else(|| "storage preflight has an invalid disk".to_string())?;
    let mut preflight = StoragePreflight {
        disk: disk.clone(),
        esp_present: false,
        esp_name: String::new(),
        windows_present: false,
        bitlocker_locked: false,
        checked_partitions: 0,
    };
    for part in parse_partitions(input)? {
        if !on_selected_disk(&part.name, &disk) {
            continue;
        }
        preflight.checked_partitions += 1;
        if part.efi && !preflight.esp_present {
            preflight.esp_present = true;
            preflight.esp_name = part.name.clone();
        }
        // `parttype`/`fstype` are already lowercased by parse_partitions.
        if matches!(part.fstype.as_str(), "ntfs" | "ntfs3")
            || part.parttype == WINDOWS_DATA_GUID
            || part.label.to_ascii_lowercase().contains("windows")
        {
            preflight.windows_present = true;
        }
        // An explicit BitLocker type, or an NTFS volume with active
        // mappings: the locked-BitLocker shape the Python
        // `_encryption_check` compat path warns on.
        if part.fstype == "bitlocker"
            || (matches!(part.fstype.as_str(), "ntfs" | "ntfs3") && part.in_use)
        {
            preflight.bitlocker_locked = true;
        }
    }
    Ok(preflight)
}

/// Fail closed on locked BitLocker in every mode; require an existing ESP
/// to preserve for every mode where bootc does not own the whole-disk
/// layout (`wipe` recreates the ESP via `bootc to-disk`).
pub(crate) fn validate_storage_preflight(
    preflight: &StoragePreflight,
    install_mode: &str,
) -> Result<(), String> {
    if preflight.bitlocker_locked {
        return Err(
            "This disk has a locked BitLocker volume. Suspend or disable BitLocker in Windows (manage-bde -off) and wait for decryption before installing."
                .to_string(),
        );
    }
    if install_mode != "wipe" && !preflight.esp_present {
        return Err(
            "No EFI System Partition was found on the target disk. The installer preserves the existing ESP instead of formatting it; select a disk with an ESP or erase the disk."
                .to_string(),
        );
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    const SNAPSHOT: &str = include_str!("../testdata/lsblk_snapshot.json");

    #[test]
    fn parses_and_filters_disk_snapshot() {
        let disks = parse_disks(SNAPSHOT, &["/dev/sdb".to_string()], Some("/dev/sda"))
            .expect("snapshot should parse");
        assert_eq!(disks.len(), 1);
        assert_eq!(disks[0].name, "/dev/sda");
        assert!(disks[0].current);
        assert_eq!(disks[0].partition_table, "gpt");
    }

    #[test]
    fn parses_partition_candidates_and_descendant_mounts() {
        let partitions = parse_partitions(SNAPSHOT).expect("snapshot should parse");
        assert_eq!(partitions.len(), 2);
        assert!(partitions[0].efi);
        assert!(!partitions[0].alongside_candidate);
        assert!(partitions[1].in_use);
        assert!(partitions[1].current);
        assert!(!partitions[1].ntfs_resize_candidate);
        assert!(partitions[1]
            .mountpoints
            .iter()
            .any(|mount| mount == "/mnt"));
    }

    #[test]
    fn windows_partitions_are_never_alongside_candidates() {
        let snapshot = r#"{"blockdevices":[{"name":"/dev/sda","type":"disk","children":[
            {"name":"/dev/sda1","type":"part","size":137438953472,"fstype":"ntfs","parttype":"ebd0a0a2-b9e5-4433-87c0-68b6b72699c7","mountpoints":[]},
            {"name":"/dev/sda2","type":"part","size":137438953472,"fstype":"ext4","mountpoints":[]}
        ]}]}"#;
        let partitions = parse_partitions(snapshot).expect("snapshot should parse");
        assert_eq!(partitions.len(), 2);
        assert!(!partitions[0].alongside_candidate);
        assert!(partitions[0].ntfs_resize_candidate);
        assert!(partitions[1].alongside_candidate);
        assert!(!partitions[1].ntfs_resize_candidate);
    }

    #[test]
    fn selects_efi_partition_and_reuses_only_safe_existing_mounts() {
        let efi = efi_partition_from_snapshot(SNAPSHOT, "/dev/sda")
            .expect("EFI query should parse")
            .expect("fixture has an ESP");
        assert_eq!(efi.name, "/dev/sda1");
        assert_eq!(efi.mounted_at.as_deref(), Some("/boot/efi"));
        assert!(efi_partition_from_snapshot(SNAPSHOT, "/dev/sdb")
            .unwrap()
            .is_none());

        let unsafe_mount = SNAPSHOT.replace("/boot/efi", "/run/../etc");
        let efi = efi_partition_from_snapshot(&unsafe_mount, "/dev/sda")
            .unwrap()
            .expect("ESP remains discoverable");
        assert!(efi.mounted_at.is_none());
    }

    #[test]
    fn rejects_malformed_snapshot() {
        let error = parse_partitions("not-json").expect_err("malformed JSON must fail closed");
        assert!(error.contains("invalid lsblk snapshot"));
    }

    #[test]
    fn runtime_inventory_resolves_protected_and_current_disks() {
        let ancestry = r#"{"blockdevices":[
            {"name":"/dev/sda","type":"disk"},
            {"name":"/dev/sda1","type":"part","pkname":"/dev/sda"},
            {"name":"/dev/sdb","type":"disk"},
            {"name":"/dev/sdb1","type":"part","pkname":"/dev/sdb"}
        ]}"#;
        let disks = runtime_disks_from_snapshots(
            SNAPSHOT,
            ancestry,
            &["/dev/sdb1".to_string()],
            Some("/dev/sda1"),
        )
        .expect("runtime snapshots should parse");
        assert_eq!(disks.len(), 1);
        assert_eq!(disks[0].name, "/dev/sda");
        assert!(disks[0].current);
        assert_eq!(
            parent_disk_in_snapshot(ancestry, "/dev/sdb1")
                .unwrap()
                .as_deref(),
            Some("/dev/sdb")
        );
    }

    #[test]
    fn free_regions_retain_aligned_space_and_minimum() {
        let disk_size = 100 * 1024 * 1024 * 1024_u64;
        let snapshot = format!(
            r#"{{"blockdevices":[{{"name":"/dev/sda","size":{disk_size},"type":"disk","pttype":"gpt","children":[{{"name":"/dev/sda1","size":{},"type":"part","start":2048,"parttype":"x"}}]}}]}}"#,
            32 * 1024 * 1024 * 1024_u64
        );
        let regions = free_regions(&snapshot, "/dev/sda", 512).expect("free space should parse");
        assert_eq!(regions.len(), 1);
        assert_eq!(regions[0].start_bytes % 512, 0);
        assert_eq!(regions[0].end_bytes, disk_size - GPT_RESERVE_BYTES);
        assert!(regions[0].size_bytes >= MIN_KYTHOS_BYTES + GPT_RESERVE_BYTES);
    }

    #[test]
    fn selects_btrfs_root_only_from_selected_disk() {
        let snapshot = r#"{
            "blockdevices": [
                {
                    "name": "/dev/sda",
                    "type": "disk",
                    "children": [
                        {"name": "/dev/sda1", "type": "part", "fstype": "vfat"},
                        {"name": "/dev/sda2", "type": "part", "fstype": "BTRFS"}
                    ]
                },
                {
                    "name": "/dev/sdb",
                    "type": "disk",
                    "children": [
                        {"name": "/dev/sdb1", "type": "part", "fstype": "btrfs"}
                    ]
                }
            ]
        }"#;
        assert_eq!(
            root_partition_from_snapshot(snapshot, "sda").unwrap(),
            "/dev/sda2"
        );
    }

    #[test]
    fn rejects_missing_or_unrelated_btrfs_root() {
        let no_root = r#"{
            "blockdevices": [{
                "name": "/dev/sda",
                "type": "disk",
                "children": [{"name": "/dev/sda1", "type": "part", "fstype": "vfat"}]
            }]
        }"#;
        let error = root_partition_from_snapshot(no_root, "/dev/sda")
            .expect_err("a disk without Btrfs must fail closed");
        assert!(error.contains("no Btrfs root partition"), "{error}");

        let unrelated = r#"{
            "blockdevices": [{
                "name": "/dev/sdb",
                "type": "disk",
                "children": [{"name": "/dev/sdb1", "type": "part", "fstype": "btrfs"}]
            }]
        }"#;
        let error = root_partition_from_snapshot(unrelated, "/dev/sda")
            .expect_err("an absent selected disk must fail closed");
        assert!(error.contains("target disk was not present"), "{error}");
    }

    #[test]
    fn partition_probe_requires_parent_and_reports_live_safety_fields() {
        let disk_size = 128 * 1024 * 1024 * 1024_u64;
        let partition_size = 96 * 1024 * 1024 * 1024_u64;
        let snapshot = format!(
            r#"{{"blockdevices":[{{"name":"/dev/sda","size":{disk_size},"type":"disk","pttype":"gpt","children":[{{"name":"/dev/sda1","partn":1,"size":{partition_size},"type":"part","fstype":"ntfs","start":2048,"mountpoints":[null],"ro":false}}]}}]}}"#
        );
        let partition = partition_probe_from_snapshot(&snapshot, "/dev/sda", "sda1")
            .expect("selected partition should be found");
        assert_eq!(partition.name, "/dev/sda1");
        assert_eq!(partition.number, 1);
        assert_eq!(partition.fstype, "ntfs");
        assert_eq!(partition.start_bytes, 2048 * 512);
        assert!(!partition.current);
        assert!(!partition.in_use);
        assert!(!partition.efi);
        assert!(!partition.read_only);

        assert!(partition_probe_from_snapshot(&snapshot, "/dev/sdb", "/dev/sda1").is_err());
    }

    #[test]
    fn free_region_check_rejects_stale_or_overlapping_selection() {
        let disk_size = 100 * 1024 * 1024 * 1024_u64;
        let snapshot = format!(
            r#"{{"blockdevices":[{{"name":"/dev/sda","size":{disk_size},"type":"disk","pttype":"gpt","children":[]}}]}}"#
        );
        let regions = free_regions(&snapshot, "/dev/sda", 512).unwrap();
        let region = &regions[0];
        assert!(contains_free_region(
            &snapshot,
            "/dev/sda",
            region.start_bytes,
            region.end_bytes,
            512
        )
        .unwrap());
        assert!(!contains_free_region(
            &snapshot,
            "/dev/sda",
            region.start_bytes.saturating_sub(512),
            region.end_bytes,
            512
        )
        .unwrap());
    }

    #[test]
    fn new_partition_selection_requires_unique_geometry_match() {
        let before = r#"{"blockdevices":[{"name":"/dev/sda","type":"disk","children":[]}] }"#;
        let after = r#"{"blockdevices":[{"name":"/dev/sda","type":"disk","children":[
            {"name":"/dev/sda1","type":"part","size":34359738368,"start":4096}
        ]}] }"#;
        assert_eq!(
            new_partition_from_snapshots(before, after, 4096 * 512, 34359738368).unwrap(),
            "/dev/sda1"
        );
        assert!(new_partition_from_snapshots(before, after, 8192 * 512, 34359738368).is_err());
    }

    #[test]
    fn detects_bios_boot_partition_by_guid() {
        let snapshot = format!(
            r#"{{"blockdevices":[{{"name":"/dev/sda","type":"disk","children":[{{"name":"/dev/sda1","type":"part","parttype":"{}"}}]}}]}}"#,
            BIOS_BOOT_GUID
        );
        assert!(has_bios_boot_partition(&snapshot).unwrap());
    }

    fn preflight_snapshot(children: &str) -> String {
        format!(
            r#"{{"blockdevices":[{{"name":"/dev/sda","type":"disk","pttype":"gpt","children":[{children}]}}]}}"#
        )
    }

    #[test]
    fn preflight_detects_esp_windows_and_bitlocker_indicators() {
        let snapshot = preflight_snapshot(
            r#"{"name":"/dev/sda1","type":"part","fstype":"vfat","parttype":"c12a7328-f81f-11d2-ba4b-00a0c93ec93b","label":"ESP"},
                {"name":"/dev/sda2","type":"part","fstype":"ntfs","parttype":"ebd0a0a2-b9e5-4433-87c0-68b6b72699c7","label":"Windows"},
                {"name":"/dev/sda3","type":"part","fstype":"BitLocker","label":""},
                {"name":"/dev/sda4","type":"part","fstype":"btrfs","label":"KythOS"}"#,
        );
        let preflight =
            storage_preflight_from_snapshot(&snapshot, "/dev/sda").expect("snapshot parses");
        assert_eq!(preflight.checked_partitions, 4);
        assert!(preflight.esp_present);
        assert_eq!(preflight.esp_name, "/dev/sda1");
        assert!(preflight.windows_present);
        assert!(preflight.bitlocker_locked);
        // Another disk's partitions never leak into this disk's preflight.
        let other =
            storage_preflight_from_snapshot(&snapshot, "/dev/sdb").expect("snapshot parses");
        assert_eq!(other.checked_partitions, 0);
        assert!(!other.esp_present);
        assert!(!other.windows_present);
        assert!(!other.bitlocker_locked);
    }

    #[test]
    fn preflight_flags_ntfs_with_active_mappings_as_locked() {
        let snapshot = preflight_snapshot(
            r#"{"name":"/dev/sda1","type":"part","fstype":"ntfs","label":"Data","children":[{"name":"/dev/mapper/locked","type":"crypt"}]}"#,
        );
        let preflight = storage_preflight_from_snapshot(&snapshot, "sda").expect("snapshot parses");
        assert!(preflight.windows_present);
        assert!(preflight.bitlocker_locked);
        assert!(!preflight.esp_present);
    }

    #[test]
    fn preflight_validation_fails_closed_on_bitlocker_and_missing_esp() {
        let locked = StoragePreflight {
            disk: "/dev/sda".to_string(),
            esp_present: true,
            esp_name: "/dev/sda1".to_string(),
            windows_present: true,
            bitlocker_locked: true,
            checked_partitions: 2,
        };
        for mode in ["wipe", "alongside", "resize_ntfs", "free_space", "manual"] {
            let error = validate_storage_preflight(&locked, mode)
                .expect_err("locked BitLocker must fail closed");
            assert!(error.contains("BitLocker"), "{error}");
        }
        let no_esp = StoragePreflight {
            bitlocker_locked: false,
            esp_present: false,
            esp_name: String::new(),
            ..locked.clone()
        };
        // Wipe recreates the ESP via bootc to-disk; every other mode must
        // preserve an existing one.
        assert!(validate_storage_preflight(&no_esp, "wipe").is_ok());
        for mode in ["alongside", "resize_ntfs", "free_space", "manual"] {
            let error = validate_storage_preflight(&no_esp, mode)
                .expect_err("missing ESP must fail closed");
            assert!(error.contains("EFI System Partition"), "{error}");
        }
        let clean = StoragePreflight {
            esp_present: true,
            ..no_esp.clone()
        };
        assert!(validate_storage_preflight(&clean, "alongside").is_ok());
        assert!(
            storage_preflight_from_snapshot("not-json", "/dev/sda").is_err()
                && storage_preflight_from_snapshot("{}", "../../etc").is_err()
        );
    }

    /// Two disks: sda holds an ESP plus a spread of replace candidates; sdb
    /// holds an empty partition that belongs to a *different* disk.
    const REPLACE_SNAPSHOT: &str = r#"{"blockdevices":[
        {"name":"/dev/sda","type":"disk","size":1099511627776,"children":[
            {"name":"/dev/sda1","type":"part","partn":1,"size":536870912,"start":2048,"fstype":"vfat","parttype":"c12a7328-f81f-11d2-ba4b-00a0c93ec93b","mountpoints":[null]},
            {"name":"/dev/sda2","type":"part","partn":2,"size":137438953472,"start":1050624,"fstype":"exfat","label":"Photos","mountpoints":[null]},
            {"name":"/dev/sda3","type":"part","partn":3,"size":137438953472,"start":269486080,"fstype":"ntfs","mountpoints":[null]},
            {"name":"/dev/sda4","type":"part","partn":4,"size":137438953472,"start":537921536,"fstype":"ext4","label":"backups","mountpoints":[null]},
            {"name":"/dev/sda5","type":"part","partn":5,"size":137438953472,"start":806356992,"fstype":"","mountpoints":[null]},
            {"name":"/dev/sda6","type":"part","partn":6,"size":137438953472,"start":1074792448,"fstype":"btrfs","label":"KythOS","mountpoints":[null]},
            {"name":"/dev/sda7","type":"part","partn":7,"size":1073741824,"start":1343227904,"fstype":"","mountpoints":[null]},
            {"name":"/dev/sda8","type":"part","partn":8,"size":137438953472,"start":1345325056,"fstype":"apfs","mountpoints":[null]}
        ]},
        {"name":"/dev/sdb","type":"disk","size":274877906944,"children":[
            {"name":"/dev/sdb1","type":"part","partn":1,"size":137438953472,"start":2048,"fstype":"","mountpoints":[null]}
        ]}
    ]}"#;

    #[test]
    fn replace_target_refuses_partitions_that_hold_someone_elses_data() {
        // The alongside/manual commit runs mkfs.btrfs -f on this partition.
        // Before this gate, nothing between the frontend and the format
        // re-checked the partition itself: an exFAT photo library, an
        // unlocked Windows NTFS volume, or an APFS volume would be wiped.
        for (partition, needle) in [
            ("/dev/sda2", "exfat filesystem labeled \"Photos\""),
            ("/dev/sda3", "ntfs filesystem"),
            ("/dev/sda8", "apfs filesystem"),
            ("/dev/sda4", "labeled ext4 volume (\"backups\")"),
        ] {
            let error = validate_replace_target(
                REPLACE_SNAPSHOT,
                "/dev/sda",
                partition,
                "target partition",
            )
            .expect_err(partition);
            assert!(error.contains(needle), "{partition}: {error}");
        }
    }

    #[test]
    fn replace_target_refuses_esp_small_and_cross_disk_partitions() {
        let esp =
            validate_replace_target(REPLACE_SNAPSHOT, "/dev/sda", "/dev/sda1", "root partition")
                .unwrap_err();
        assert!(esp.contains("EFI system partition"), "{esp}");
        let small = validate_replace_target(
            REPLACE_SNAPSHOT,
            "/dev/sda",
            "/dev/sda7",
            "target partition",
        )
        .unwrap_err();
        assert!(small.contains("too small"), "{small}");
        // Every other safety gate validates `disk`; the format runs on
        // `target_partition`. They must be the same disk.
        let cross_disk = validate_replace_target(
            REPLACE_SNAPSHOT,
            "/dev/sda",
            "/dev/sdb1",
            "target partition",
        )
        .unwrap_err();
        assert!(
            cross_disk.contains("not present on the target disk"),
            "{cross_disk}"
        );
    }

    #[test]
    fn replace_target_accepts_empty_and_existing_kythos_btrfs_partitions() {
        for partition in ["/dev/sda5", "/dev/sda6"] {
            let probe = validate_replace_target(
                REPLACE_SNAPSHOT,
                "/dev/sda",
                partition,
                "target partition",
            )
            .unwrap_or_else(|error| panic!("{partition}: {error}"));
            assert_eq!(probe.name, partition);
        }
    }

    fn bios_snapshot(pttype: &str, sda_parts: &str, sdb_parts: &str) -> String {
        format!(
            r#"{{"blockdevices":[
                {{"name":"/dev/sda","type":"disk","size":1099511627776,"pttype":"{pttype}","children":[{sda_parts}]}},
                {{"name":"/dev/sdb","type":"disk","size":274877906944,"pttype":"gpt","children":[{sdb_parts}]}}
            ]}}"#
        )
    }

    #[test]
    fn alongside_refuses_legacy_bios_gpt_without_a_bios_boot_partition() {
        let esp = r#"{"name":"/dev/sda1","type":"part","parttype":"c12a7328-f81f-11d2-ba4b-00a0c93ec93b"}"#;
        let bios = format!(r#"{{"name":"/dev/sda2","type":"part","parttype":"{BIOS_BOOT_GUID}"}}"#);
        let other_disk_bios =
            format!(r#"{{"name":"/dev/sdb1","type":"part","parttype":"{BIOS_BOOT_GUID}"}}"#);

        // Legacy BIOS + GPT + no BIOS boot partition: GRUB cannot boot Btrfs.
        let missing = bios_snapshot("gpt", esp, "");
        let error = validate_alongside_bios_boot(&missing, "/dev/sda", false).unwrap_err();
        assert!(error.contains("BIOS boot partition"), "{error}");
        // A BIOS boot partition on a different disk does not help this one.
        let elsewhere = bios_snapshot("gpt", esp, &other_disk_bios);
        assert!(validate_alongside_bios_boot(&elsewhere, "/dev/sda", false).is_err());

        // UEFI boots, MBR disks, and disks that already have one are fine.
        assert!(validate_alongside_bios_boot(&missing, "/dev/sda", true).is_ok());
        let mbr = bios_snapshot("dos", esp, "");
        assert!(validate_alongside_bios_boot(&mbr, "/dev/sda", false).is_ok());
        let present = bios_snapshot("gpt", &format!("{esp},{bios}"), "");
        assert!(validate_alongside_bios_boot(&present, "/dev/sda", false).is_ok());

        // An unknown disk fails closed rather than skipping the check.
        assert!(validate_alongside_bios_boot(&missing, "/dev/sdz", false).is_err());
    }

    #[test]
    fn alongside_candidates_match_the_commit_content_gate() {
        let partitions = parse_partitions(REPLACE_SNAPSHOT).expect("snapshot should parse");
        let offered: Vec<&str> = partitions
            .iter()
            .filter(|part| part.alongside_candidate)
            .map(|part| part.name.as_str())
            .collect();
        assert_eq!(offered, ["/dev/sda5", "/dev/sda6", "/dev/sdb1"]);
    }
}
