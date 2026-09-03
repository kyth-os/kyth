//! Immutable metadata model for staged partition operations.
//!
//! This module owns the pure journal model and validation contract. It owns no
//! disk handles and performs no partition work; the Python journal still
//! controls lifecycle and operation execution.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{HashMap, HashSet};

use crate::installer_plan::normalize_device_path;
use crate::installer_storage::PartitionRecord;

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub(crate) struct PartitionOperation {
    pub kind: String,
    pub params: Value,
    pub index: usize,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub(crate) struct PartitionJournal {
    pub disk: String,
    pub ops: Vec<PartitionOperation>,
    pub committed: bool,
    pub root_partition: Option<String>,
    pub irreversible_completed: bool,
}

#[derive(Debug, Deserialize)]
pub(crate) struct JournalValidationInput {
    pub journal: PartitionJournal,
    pub current_parts: Vec<PartitionRecord>,
    pub table_type: String,
    pub disk_size_bytes: u64,
}

pub(crate) fn validate_request(input: JournalValidationInput) -> serde_json::Value {
    let errors = validate(
        &input.journal,
        &input.current_parts,
        &input.table_type,
        input.disk_size_bytes,
    );
    serde_json::json!({
        "valid": errors.is_empty(),
        "errors": errors,
    })
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(crate) struct ManualMount {
    pub partition: String,
    pub mountpoint: String,
    pub fstype: String,
}

impl PartitionJournal {
    pub(crate) fn new(disk: &str) -> Result<Self, String> {
        let disk = normalize_device_path(disk)
            .ok_or_else(|| "Invalid disk path for journal.".to_string())?;
        Ok(Self {
            disk,
            ops: Vec::new(),
            committed: false,
            root_partition: None,
            irreversible_completed: false,
        })
    }

    /// Append an operation and assign the same list-length identity as the
    /// Python compatibility journal. Removing an operation does not rewrite
    /// existing identities, so durable event references remain stable.
    pub(crate) fn add_op(&mut self, kind: impl Into<String>, params: Value) -> usize {
        let index = self.ops.len();
        self.ops.push(PartitionOperation {
            kind: kind.into(),
            params,
            index,
        });
        index
    }

    pub(crate) fn remove_op(&mut self, index: usize) -> bool {
        if index >= self.ops.len() {
            return false;
        }
        self.ops.remove(index);
        true
    }

    pub(crate) fn clear(&mut self) {
        self.ops.clear();
    }

    pub(crate) fn pending(&self) -> Vec<PartitionOperation> {
        self.ops.clone()
    }

    pub(crate) fn mark_committed(&mut self, root_partition: Option<&str>) -> Result<(), String> {
        self.root_partition = match root_partition {
            Some(value) => Some(
                normalize_device_path(value)
                    .ok_or_else(|| "Invalid root partition for journal.".to_string())?,
            ),
            None => None,
        };
        self.committed = true;
        Ok(())
    }

    pub(crate) fn rollback_metadata(&mut self) {
        self.clear();
        self.committed = false;
        self.root_partition = None;
        self.irreversible_completed = false;
    }
}

fn value_string(params: &Value, key: &str) -> String {
    params
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_string()
}

fn value_i64(params: &Value, key: &str, default: i64) -> i64 {
    match params.get(key) {
        Some(Value::Number(value)) => value.as_i64().unwrap_or(default),
        Some(Value::String(value)) => value.parse::<i64>().unwrap_or(default),
        _ => default,
    }
}

fn last_mountpoint_indices(journal: &PartitionJournal) -> HashMap<String, usize> {
    let mut last = HashMap::new();
    for operation in &journal.ops {
        if operation.kind == "set_mountpoint" {
            let partition = value_string(&operation.params, "partition");
            if !partition.is_empty() {
                last.insert(partition, operation.index);
            }
        }
    }
    last
}

/// Project non-root manual mounts from a committed journal and a fresh,
/// read-only partition snapshot.
///
/// This mirrors `kyth_installer.plan_query.get_manual_mounts`. It does not
/// inspect or mutate devices; the caller supplies post-commit discovery data
/// and remains responsible for deciding when to invoke it.
pub(crate) fn manual_mounts(
    journal: &PartitionJournal,
    current_parts: &[PartitionRecord],
) -> Result<Vec<ManualMount>, String> {
    if !journal.committed {
        return Ok(Vec::new());
    }
    if journal.disk.trim().is_empty() {
        return Err("Committed partition journal has no target disk.".to_string());
    }

    let discovered: HashMap<&str, &PartitionRecord> = current_parts
        .iter()
        .map(|part| (part.name.as_str(), part))
        .collect();
    let created: HashSet<String> = journal
        .ops
        .iter()
        .filter(|operation| operation.kind == "create")
        .map(|operation| value_string(&operation.params, "partition"))
        .filter(|partition| !partition.is_empty())
        .collect();

    let mut mounts = Vec::new();
    let mut assigned_mountpoints = HashSet::new();
    let mut assigned_partitions = HashSet::new();
    for operation in &journal.ops {
        if !matches!(operation.kind.as_str(), "create" | "set_mountpoint") {
            continue;
        }
        if !operation.params.is_object() {
            return Err("Committed partition journal contains malformed operations.".to_string());
        }
        let mountpoint = value_string(&operation.params, "mountpoint");
        let partition = value_string(&operation.params, "partition");
        if mountpoint.is_empty()
            || matches!(mountpoint.as_str(), "/" | "/boot/efi")
            || partition.is_empty()
        {
            continue;
        }
        if !discovered.contains_key(partition.as_str()) && !created.contains(&partition) {
            return Err(format!(
                "Manual mount target {partition} disappeared after partition commit."
            ));
        }
        if !assigned_mountpoints.insert(mountpoint.clone()) {
            return Err(format!(
                "Manual mount point {mountpoint} is assigned more than once."
            ));
        }
        if !assigned_partitions.insert(partition.clone()) {
            return Err(format!(
                "Manual partition {partition} has multiple mount assignments."
            ));
        }

        let mut fstype = if operation.kind == "create" {
            value_string(&operation.params, "fs_type")
        } else {
            String::new()
        };
        for format_operation in &journal.ops {
            if format_operation.kind != "format" {
                continue;
            }
            if !format_operation.params.is_object() {
                return Err("Committed partition journal contains malformed operations.".to_string());
            }
            if value_string(&format_operation.params, "partition") == partition {
                fstype = value_string(&format_operation.params, "fs_type");
                break;
            }
        }
        if fstype.is_empty() {
            fstype = discovered
                .get(partition.as_str())
                .map(|part| part.fstype.clone())
                .unwrap_or_default();
        }
        mounts.push(ManualMount {
            partition,
            mountpoint,
            fstype: if fstype.is_empty() {
                "btrfs".to_string()
            } else {
                fstype
            },
        });
    }
    Ok(mounts)
}

/// Validate staged journal metadata against an explicit, read-only snapshot.
/// This mirrors the Python journal's safety checks but never touches devices.
pub(crate) fn validate(
    journal: &PartitionJournal,
    current_parts: &[PartitionRecord],
    table_type: &str,
    disk_size_bytes: u64,
) -> Vec<String> {
    if journal.ops.is_empty() {
        return vec!["No partition operations have been added.".to_string()];
    }

    let mut errors = Vec::new();
    let mut root_count = 0;
    let mut mountpoints = HashSet::new();
    let mut allocated: HashMap<String, (i64, i64, String)> = current_parts
        .iter()
        .map(|part| {
            (
                part.name.clone(),
                (
                    part.start_bytes as i64,
                    part.start_bytes.saturating_add(part.size_bytes) as i64,
                    part.fstype.clone(),
                ),
            )
        })
        .collect();
    let mut table = table_type.to_ascii_lowercase();
    let mut primary_count = if table == "msdos" {
        current_parts.len()
    } else {
        0
    };
    let last_mountpoints = last_mountpoint_indices(journal);

    for operation in &journal.ops {
        let params = &operation.params;
        if operation.kind == "set_mountpoint" {
            let partition = value_string(params, "partition");
            if !partition.is_empty() && last_mountpoints.get(&partition) != Some(&operation.index) {
                continue;
            }
        }

        match operation.kind.as_str() {
            "new_table" => {
                allocated.clear();
                root_count = 0;
                mountpoints.clear();
                table = {
                    let value = value_string(params, "table_type");
                    if value.is_empty() { "gpt".to_string() } else { value.to_ascii_lowercase() }
                };
                primary_count = 0;
                if table == "gpt" {
                    allocated.insert(
                        "automatic BIOS boot partition".to_string(),
                        (1024 * 1024, 2 * 1024 * 1024, "bios_grub".to_string()),
                    );
                }
            }
            "create" => {
                let start = value_i64(params, "start_bytes", -1);
                let size = value_i64(params, "size_bytes", -1);
                let fs = value_string(params, "fs_type").to_ascii_lowercase();
                let mount = value_string(params, "mountpoint").to_ascii_lowercase();
                if start < 0 || size < 0 {
                    errors.push("Create partition: invalid start or size.".to_string());
                }
                let end = start.saturating_add(size);
                if start >= 0 && size >= 0 {
                    for (name, (other_start, other_end, _)) in &allocated {
                        if *other_start >= 0 && *other_end > *other_start && start < *other_end && end > *other_start {
                            errors.push(format!("New partition overlaps with existing region ({name})."));
                            break;
                        }
                    }
                }
                if table == "msdos" && primary_count >= 4 {
                    errors.push(
                        "MBR (msdos) partition tables support at most 4 primary partitions, and this installer does not create extended/logical partitions. Use a GPT table instead, or remove a partition from this layout.".to_string(),
                    );
                }
                if mount == "/" && fs != "btrfs" {
                    errors.push("Root partition (/) must use the Btrfs filesystem.".to_string());
                }
                if mount == "/boot/efi" && fs != "fat32" {
                    errors.push("EFI System Partition (/boot/efi) must use FAT32.".to_string());
                }
                if !mount.is_empty() && mountpoints.contains(&mount) {
                    errors.push(format!("Mount point {mount} is assigned more than once."));
                }
                allocated.insert(format!("new:{}", operation.index), (start, end, fs));
                if table == "msdos" {
                    primary_count += 1;
                }
                if mount == "/" {
                    root_count += 1;
                }
                if !mount.is_empty() {
                    mountpoints.insert(mount);
                }
            }
            "delete" | "format" | "resize" | "set_mountpoint" => {
                let raw_partition = value_string(params, "partition");
                let partition = normalize_device_path(&raw_partition);
                let Some(partition) = partition else {
                    errors.push(format!("{}: partition does not belong to {}.", operation.kind, journal.disk));
                    continue;
                };
                let Some((start, end, fs)) = allocated.get(&partition).cloned() else {
                    errors.push(format!("{}: {partition} is not present on {}.", operation.kind, journal.disk));
                    continue;
                };
                let mut valid = true;
                if operation.kind == "resize" {
                    let new_size = value_i64(params, "new_size_bytes", -1);
                    if new_size <= 0 {
                        errors.push("Resize partition: invalid new size.".to_string());
                        valid = false;
                    } else {
                        let new_end = start.saturating_add(new_size);
                        if disk_size_bytes > 0 && new_end as u64 > disk_size_bytes {
                            errors.push(format!("Resize partition: new size for {partition} extends past the end of {}.", journal.disk));
                            valid = false;
                        }
                        for (name, (other_start, other_end, _)) in &allocated {
                            if name != &partition && *other_start >= 0 && *other_end > *other_start && start < *other_end && new_end > *other_start {
                                errors.push(format!("Resize partition: new size for {partition} would overlap with existing region ({name})."));
                                valid = false;
                                break;
                            }
                        }
                    }
                } else if operation.kind == "set_mountpoint" {
                    let mount = value_string(params, "mountpoint");
                    if mount == "/" && fs != "btrfs" {
                        errors.push("Root partition (/) must use the Btrfs filesystem.".to_string());
                        valid = false;
                    }
                    if mount == "/boot/efi" && !matches!(fs.as_str(), "fat" | "fat32" | "vfat") {
                        errors.push("EFI System Partition (/boot/efi) must use FAT32.".to_string());
                        valid = false;
                    }
                    if !mount.is_empty() && mountpoints.contains(&mount) {
                        errors.push(format!("Mount point {mount} is assigned more than once."));
                        valid = false;
                    }
                    if valid {
                        if mount == "/" { root_count += 1; }
                        if !mount.is_empty() { mountpoints.insert(mount); }
                    }
                }
                if valid {
                    match operation.kind.as_str() {
                        "delete" => {
                            allocated.remove(&partition);
                            if table == "msdos" { primary_count = primary_count.saturating_sub(1); }
                        }
                        "resize" => {
                            let new_size = value_i64(params, "new_size_bytes", -1);
                            allocated.insert(partition, (start, start.saturating_add(new_size), fs));
                        }
                        "format" => {
                            allocated.insert(partition, (start, end, value_string(params, "fs_type").to_ascii_lowercase()));
                        }
                        _ => {}
                    }
                }
            }
            _ => {}
        }
    }

    if root_count == 0 {
        errors.push("No root partition (/) configured. Mount at least one partition as '/' with Btrfs.".to_string());
    } else if root_count > 1 {
        errors.push("Exactly one root partition (/) must be configured.".to_string());
    }

    for part in current_parts.iter().filter(|part| part.current || part.in_use) {
        for operation in &journal.ops {
            let partition = normalize_device_path(&value_string(&operation.params, "partition"));
            if partition.as_deref() != Some(part.name.as_str()) {
                continue;
            }
            if matches!(operation.kind.as_str(), "delete" | "format" | "resize") {
                errors.push(format!("Cannot modify {} — it is currently mounted or in use.", part.name));
                break;
            }
            if operation.kind == "set_mountpoint"
                && value_string(&operation.params, "mountpoint") == "/"
                && last_mountpoints.get(&value_string(&operation.params, "partition")) == Some(&operation.index)
            {
                errors.push(format!("Cannot set {} as the root partition — it is currently mounted or in use.", part.name));
                break;
            }
        }
    }
    errors
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::installer_storage::PartitionRecord;
    use serde_json::json;

    fn partition(name: &str, fs: &str, current: bool) -> PartitionRecord {
        PartitionRecord {
            name: name.to_string(),
            size_bytes: 64 * 1024 * 1024 * 1024,
            start_bytes: 2 * 1024 * 1024,
            fstype: fs.to_string(),
            label: String::new(),
            parttype: String::new(),
            mountpoints: Vec::new(),
            efi: false,
            current,
            in_use: current,
            read_only: false,
            alongside_candidate: !current,
            ntfs_resize_candidate: false,
        }
    }

    #[test]
    fn creates_a_normalized_empty_journal() {
        let journal = PartitionJournal::new("sda").expect("valid disk path");
        assert_eq!(journal.disk, "/dev/sda");
        assert!(journal.ops.is_empty());
        assert!(!journal.committed);
    }

    #[test]
    fn stages_and_removes_operations_without_rewriting_identity() {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        assert_eq!(journal.add_op("create", json!({"mountpoint": "/"})), 0);
        assert_eq!(journal.add_op("set_mountpoint", json!({"mountpoint": "/home"})), 1);
        assert!(journal.remove_op(0));
        assert_eq!(journal.pending()[0].index, 1);
        assert_eq!(journal.add_op("format", json!({"fs_type": "btrfs"})), 1);
        assert!(!journal.remove_op(99));
    }

    #[test]
    fn round_trips_and_tracks_commit_metadata() {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        journal.add_op("create", json!({"size_bytes": 34359738368_u64}));
        journal
            .mark_committed(Some("sda2"))
            .expect("valid root partition");
        let encoded = serde_json::to_string(&journal).expect("journal serializes");
        let decoded: PartitionJournal = serde_json::from_str(&encoded).expect("journal parses");
        assert_eq!(decoded, journal);
        assert_eq!(decoded.root_partition.as_deref(), Some("/dev/sda2"));
        journal.rollback_metadata();
        assert!(!journal.committed);
        assert!(journal.ops.is_empty());
        assert!(journal.root_partition.is_none());
    }

    #[test]
    fn rejects_invalid_disk_and_root_paths() {
        assert!(PartitionJournal::new("../../etc/passwd").is_err());
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        assert!(journal.mark_committed(Some("../../etc/passwd")).is_err());
        assert!(!journal.committed);
    }

    #[test]
    fn validation_request_returns_bounded_json_contract() {
        let input = JournalValidationInput {
            journal: PartitionJournal {
                disk: "/dev/sda".to_string(),
                ops: vec![PartitionOperation {
                    kind: "create".to_string(),
                    params: json!({
                        "start_bytes": 2 * 1024 * 1024,
                        "size_bytes": 64 * 1024 * 1024 * 1024_u64,
                        "fs_type": "btrfs",
                        "mountpoint": "/",
                    }),
                    index: 0,
                }],
                committed: false,
                root_partition: None,
                irreversible_completed: false,
            },
            current_parts: Vec::new(),
            table_type: "gpt".to_string(),
            disk_size_bytes: 128 * 1024 * 1024 * 1024,
        };
        let response = validate_request(input);
        assert_eq!(response["valid"], true);
        assert_eq!(response["errors"], json!([]));
        let encoded = serde_json::to_vec(&response).expect("validation response serializes");
        assert!(encoded.len() < 64 * 1024);
    }

    #[test]
    fn projects_committed_manual_mounts_and_format_overrides() {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        journal.add_op(
            "set_mountpoint",
            json!({"partition": "/dev/sda2", "mountpoint": "/home"}),
        );
        journal.add_op(
            "format",
            json!({"partition": "/dev/sda2", "fs_type": "xfs"}),
        );
        journal.add_op(
            "set_mountpoint",
            json!({"partition": "/dev/sda3", "mountpoint": "swap"}),
        );
        journal.mark_committed(None).expect("commit metadata");

        let mounts = manual_mounts(
            &journal,
            &[
                partition("/dev/sda2", "ext4", false),
                partition("/dev/sda3", "swap", false),
            ],
        )
        .expect("manual mount projection");
        assert_eq!(mounts[0].fstype, "xfs");
        assert_eq!(mounts[1].fstype, "swap");
    }

    #[test]
    fn manual_mount_projection_skips_root_and_fails_closed() {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        journal.add_op(
            "set_mountpoint",
            json!({"partition": "/dev/sda2", "mountpoint": "/"}),
        );
        journal.add_op(
            "set_mountpoint",
            json!({"partition": "/dev/sda3", "mountpoint": "/boot/efi"}),
        );
        journal.mark_committed(None).expect("commit metadata");
        assert!(manual_mounts(&journal, &[]).expect("root mounts are skipped").is_empty());

        let mut stale = PartitionJournal::new("/dev/sda").expect("valid disk path");
        stale.add_op(
            "set_mountpoint",
            json!({"partition": "/dev/sda9", "mountpoint": "/home"}),
        );
        stale.mark_committed(None).expect("commit metadata");
        assert!(manual_mounts(&stale, &[])
            .expect_err("stale target must fail closed")
            .contains("disappeared"));

        let mut malformed = PartitionJournal::new("/dev/sda").expect("valid disk path");
        malformed.add_op("set_mountpoint", Value::Null);
        malformed.mark_committed(None).expect("commit metadata");
        assert!(manual_mounts(&malformed, &[])
            .expect_err("malformed operation must fail closed")
            .contains("malformed"));
    }

    #[test]
    fn manual_mount_projection_rejects_duplicate_assignments() {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        journal.add_op(
            "set_mountpoint",
            json!({"partition": "/dev/sda2", "mountpoint": "/home"}),
        );
        journal.add_op(
            "set_mountpoint",
            json!({"partition": "/dev/sda3", "mountpoint": "/home"}),
        );
        journal.mark_committed(None).expect("commit metadata");
        let error = manual_mounts(
            &journal,
            &[
                partition("/dev/sda2", "btrfs", false),
                partition("/dev/sda3", "btrfs", false),
            ],
        )
        .expect_err("duplicate mountpoint must fail closed");
        assert!(error.contains("assigned more than once"));
    }

    #[test]
    fn validates_a_single_btrfs_root_assignment() {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        journal.add_op("set_mountpoint", json!({"partition": "/dev/sda2", "mountpoint": "/"}));
        let errors = validate(&journal, &[partition("/dev/sda2", "btrfs", false)], "gpt", 200 * 1024 * 1024 * 1024);
        assert!(errors.is_empty(), "unexpected journal errors: {errors:?}");
    }

    #[test]
    fn rejects_duplicate_roots_overlaps_and_in_use_partitions() {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        journal.add_op("set_mountpoint", json!({"partition": "/dev/sda2", "mountpoint": "/"}));
        journal.add_op("set_mountpoint", json!({"partition": "/dev/sda3", "mountpoint": "/"}));
        journal.add_op("create", json!({"start_bytes": 2 * 1024 * 1024_u64, "size_bytes": 64_u64 * 1024 * 1024 * 1024, "fs_type": "btrfs", "mountpoint": "/home"}));
        journal.add_op("format", json!({"partition": "/dev/sda2", "fs_type": "btrfs"}));
        let errors = validate(
            &journal,
            &[
                partition("/dev/sda2", "btrfs", true),
                partition("/dev/sda3", "btrfs", false),
            ],
            "gpt",
            200 * 1024 * 1024 * 1024,
        );
        assert!(errors.iter().any(|error| error.contains("assigned more than once")));
        assert!(errors.iter().any(|error| error.contains("overlaps")));
        assert!(errors.iter().any(|error| error.contains("Cannot set /dev/sda2")));
    }

    #[test]
    fn shared_journal_fixture_matches_rust_validation() {
        #[derive(Deserialize)]
        struct FixtureOp {
            kind: String,
            params: Value,
        }

        #[derive(Deserialize)]
        struct Case {
            name: String,
            table_type: String,
            disk_size_bytes: u64,
            partitions: Vec<PartitionRecord>,
            ops: Vec<FixtureOp>,
            expected_errors: Vec<String>,
        }

        let cases: Vec<Case> = serde_json::from_str(include_str!("../testdata/journal_cases.json"))
            .expect("journal parity fixture must be valid JSON");
        for case in cases {
            let mut journal = PartitionJournal::new("/dev/sda").expect("fixture disk path");
            for operation in case.ops {
                journal.add_op(operation.kind, operation.params);
            }
            let errors = validate(&journal, &case.partitions, &case.table_type, case.disk_size_bytes);
            for expected in case.expected_errors {
                assert!(errors.iter().any(|error| error.contains(&expected)), "{}: {errors:?}", case.name);
            }
            if case.name == "single-btrfs-root" {
                assert!(errors.is_empty(), "{}: {errors:?}", case.name);
            }
        }
    }
}
