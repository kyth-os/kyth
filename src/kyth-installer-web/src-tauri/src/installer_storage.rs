//! Read-only `lsblk --json --bytes` snapshot parsing for installer discovery.
//!
//! The parser accepts an explicit snapshot rather than spawning a command or
//! touching devices. Runtime probing and protected-disk policy remain outside
//! this first port; the Python service remains authoritative until parity is
//! complete.

use serde::{Deserialize, Serialize};

const EFI_PART_GUID: &str = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b";
const MIN_KYTHOS_BYTES: u64 = 32 * 1024 * 1024 * 1024;
const NTFS_MIN_BYTES: u64 = (64 + 32) * 1024 * 1024 * 1024;

#[derive(Debug, Deserialize)]
struct LsblkSnapshot {
    #[serde(default)]
    blockdevices: Vec<LsblkDevice>,
}

#[derive(Debug, Deserialize)]
struct LsblkDevice {
    name: Option<String>,
    size: Option<u64>,
    #[serde(rename = "type")]
    device_type: Option<String>,
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

#[derive(Debug, Serialize, PartialEq, Eq)]
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
            byte.is_ascii_alphanumeric()
                || matches!(byte, b'.' | b'_' | b'/' | b'+' | b':' | b'-')
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

/// Parse safe, writable whole-disk records from an explicit lsblk snapshot.
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
                partition_table: device.pttype.clone().unwrap_or_default().to_ascii_lowercase(),
            })
        })
        .collect())
}

/// Parse partition records, including descendant mounts, from an lsblk tree.
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
                    let alongside_candidate = size_bytes >= MIN_KYTHOS_BYTES
                        && !efi
                        && !current
                        && !in_use
                        && !read_only;
                    let ntfs_resize_candidate = alongside_candidate
                        && matches!(fstype.as_str(), "ntfs" | "ntfs3")
                        && size_bytes >= NTFS_MIN_BYTES;
                    partitions.push(PartitionRecord {
                        name,
                        size_bytes,
                        start_bytes: device.start.unwrap_or(0).saturating_mul(512),
                        fstype,
                        label: device.label.clone().unwrap_or_default(),
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
        assert!(partitions[1].mountpoints.iter().any(|mount| mount == "/mnt"));
    }

    #[test]
    fn rejects_malformed_snapshot() {
        let error = parse_partitions("not-json").expect_err("malformed JSON must fail closed");
        assert!(error.contains("invalid lsblk snapshot"));
    }
}
