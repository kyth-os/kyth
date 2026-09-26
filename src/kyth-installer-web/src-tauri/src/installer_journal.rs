//! Immutable metadata model for staged partition operations.
//!
//! This module owns the journal model, target validation, and native execution
//! boundary. Python journal code is retained only as a source fixture.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{HashMap, HashSet};
use std::fs::{File, OpenOptions};
use std::io::Write;
use std::os::fd::AsRawFd;
use std::os::unix::fs::OpenOptionsExt;
use std::os::unix::process::CommandExt;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

use crate::installer_disk;
use crate::installer_plan::normalize_device_path;
use crate::installer_storage;
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

#[derive(Debug, Deserialize)]
pub(crate) struct JournalTargetInput {
    pub disk: String,
    pub partition: String,
}

#[derive(Debug, Deserialize)]
pub(crate) struct JournalCommitInput {
    pub journal: PartitionJournal,
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

pub(crate) fn validate_target_request(input: JournalTargetInput) -> serde_json::Value {
    let disk = normalize_device_path(&input.disk);
    let partition = normalize_device_path(&input.partition);
    let error = match (disk, partition) {
        (Some(disk), Some(partition)) => {
            let suffix = partition.strip_prefix(&disk).unwrap_or_default();
            let partition_name_matches = if disk
                .chars()
                .last()
                .is_some_and(|value| value.is_ascii_digit())
            {
                suffix.strip_prefix('p').is_some_and(|value| {
                    !value.is_empty() && value.bytes().all(|byte| byte.is_ascii_digit())
                })
            } else {
                !suffix.is_empty() && suffix.bytes().all(|byte| byte.is_ascii_digit())
            };
            if !partition_name_matches {
                Some(format!(
                    "Partition {partition} does not belong to the active disk {disk}."
                ))
            } else {
                match runtime_partition_records(&disk) {
                    Ok(parts) if parts.iter().any(|part| part.name == partition) => None,
                    Ok(_) => Some(format!(
                        "Partition {partition} is not present on the active disk {disk}."
                    )),
                    Err(error) => Some(error),
                }
            }
        }
        _ => Some("Disk and partition must be safe device paths.".to_string()),
    };
    serde_json::json!({
        "valid": error.is_none(),
        "partition": normalize_device_path(&input.partition),
        "error": error,
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
        // A removed entry leaves a gap. Reuse the list length here and we
        // can assign an ID that is still held by a later operation.
        let index = self
            .ops
            .iter()
            .map(|operation| operation.index)
            .max()
            .map_or(0, |last| last.saturating_add(1));
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

/// Surfaced on every destructive commit path. Shrinking, deleting, or
/// reformatting a partition destroys data the installer cannot restore.
pub(crate) const IRREVERSIBLE_WARNING: &str =
    "This operation cannot be undone: shrinking, deleting, or reformatting \
a partition destroys data the installer cannot restore. Verify the target, \
connect AC power, and keep a GPT backup on external media before committing.";

/// True when `path` names a file on external media (`/run/media/…` or
/// `/mnt/…`) — the only acceptable home for a GPT backup, since a backup
/// on the disk being repartitioned dies with it.
pub(crate) fn path_on_external_media(path: &str) -> bool {
    let path = path.trim();
    if !path.starts_with('/') || path.contains("..") {
        return false;
    }
    matches!(path, _ if path.starts_with("/run/media/") || path.starts_with("/mnt/"))
}

/// Shrink-commit preconditions for a `resize` op, attested by the daemon in
/// the op params at commit time from live checks:
///
/// * `gpt_backup_path`: absolute path of the GPT backup file
///   (`sgdisk --backup=…`) on external media. Required for every shrink —
///   a failed shrink without a table backup is unrecoverable.
/// * `ntfs_verified_clean`: fresh re-verification that an NTFS volume's
///   dirty bit is clear, taken immediately pre-shrink (not at probe time —
///   Windows may have run since). Required for `ntfs`/`ntfs3`.
/// * `on_ac_power`: adapter confirmed online at commit time. Required for
///   every shrink — power loss mid-shrink cannot be undone.
///
/// Every refusal names the missing attestation and carries
/// [`IRREVERSIBLE_WARNING`].
pub(crate) fn validate_shrink_preconditions(fstype: &str, params: &Value) -> Vec<String> {
    let mut errors = Vec::new();
    let backup = value_string(params, "gpt_backup_path");
    if backup.is_empty() {
        errors.push(format!(
            "Shrink partition: a GPT backup file path is required before this shrink commits. {IRREVERSIBLE_WARNING}"
        ));
    } else if !path_on_external_media(&backup) {
        errors.push(format!(
            "Shrink partition: GPT backup {backup:?} must be on external media (/run/media/…, /mnt/…) — \
a backup on the disk being shrunk is lost with it. {IRREVERSIBLE_WARNING}"
        ));
    }
    if matches!(fstype, "ntfs" | "ntfs3")
        && !matches!(params.get("ntfs_verified_clean"), Some(Value::Bool(true)))
    {
        errors.push(format!(
            "Shrink partition: the NTFS dirty bit must be re-verified clear immediately pre-shrink \
(Windows may have run since the probe). {IRREVERSIBLE_WARNING}"
        ));
    }
    if !matches!(params.get("on_ac_power"), Some(Value::Bool(true))) {
        errors.push(format!(
            "Shrink partition: AC power must be confirmed online before this shrink commits — \
losing power mid-shrink cannot be undone. {IRREVERSIBLE_WARNING}"
        ));
    }
    errors
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
    let mut created = HashSet::new();
    let mut assignments = std::collections::BTreeMap::<String, String>::new();
    let mut formats = HashMap::<String, String>::new();
    for operation in &journal.ops {
        if !operation.params.is_object()
            && matches!(
                operation.kind.as_str(),
                "create" | "set_mountpoint" | "delete" | "format"
            )
        {
            return Err("Committed partition journal contains malformed operations.".to_string());
        }
        let partition = value_string(&operation.params, "partition");
        match operation.kind.as_str() {
            "new_table" => {
                assignments.clear();
                formats.clear();
                created.clear();
            }
            "create" => {
                if partition.is_empty() {
                    continue;
                }
                created.insert(partition.clone());
                let mountpoint = value_string(&operation.params, "mountpoint");
                if mountpoint.is_empty() {
                    assignments.remove(&partition);
                } else {
                    assignments.insert(partition.clone(), mountpoint);
                }
                let fs = value_string(&operation.params, "fs_type");
                if !fs.is_empty() {
                    formats.insert(partition, fs);
                }
            }
            "set_mountpoint" => {
                if partition.is_empty() {
                    continue;
                }
                let mountpoint = value_string(&operation.params, "mountpoint");
                if mountpoint.is_empty() {
                    assignments.remove(&partition);
                } else {
                    assignments.insert(partition, mountpoint);
                }
            }
            "delete" => {
                assignments.remove(&partition);
                formats.remove(&partition);
                created.remove(&partition);
            }
            "format" => {
                let fs = value_string(&operation.params, "fs_type");
                if !partition.is_empty() && !fs.is_empty() {
                    formats.insert(partition, fs);
                }
            }
            _ => {}
        }
    }

    let mut mounts = Vec::new();
    let mut assigned_mountpoints = HashSet::new();
    for (partition, mountpoint) in assignments {
        if mountpoint.is_empty() || matches!(mountpoint.as_str(), "/" | "/boot/efi") {
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
        let fstype = formats
            .get(&partition)
            .cloned()
            .or_else(|| {
                discovered
                    .get(partition.as_str())
                    .map(|part| part.fstype.clone())
            })
            .filter(|fstype| !fstype.is_empty())
            .unwrap_or_else(|| "btrfs".to_string());
        mounts.push(ManualMount {
            partition,
            mountpoint,
            fstype,
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
    let mut mount_assignments: HashMap<String, String> = HashMap::new();
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
    if table == "dos" {
        table = "msdos".to_string();
    }
    if !matches!(table.as_str(), "gpt" | "msdos" | "dos") {
        errors.push(format!("Unsupported partition table type: {table}."));
    }
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
                table = {
                    let value = value_string(params, "table_type");
                    if value.is_empty() {
                        "gpt".to_string()
                    } else {
                        value.to_ascii_lowercase()
                    }
                };
                if table == "dos" {
                    table = "msdos".to_string();
                }
                if !matches!(table.as_str(), "gpt" | "msdos" | "dos") {
                    errors.push(format!("Unsupported partition table type: {table}."));
                }
                primary_count = 0;
                mount_assignments.clear();
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
                if start <= 0 || size <= 0 {
                    errors.push("Create partition: invalid start or size.".to_string());
                }
                let end = start.saturating_add(size);
                if start > 0 && size > 0 {
                    if start % 512 != 0 || size % 512 != 0 {
                        errors.push(
                            "Create partition: start and size must align to 512-byte sectors."
                                .to_string(),
                        );
                    }
                    if disk_size_bytes > 0 && end as u64 > disk_size_bytes {
                        errors.push(format!(
                            "Create partition: new partition extends past the end of {}.",
                            journal.disk
                        ));
                    }
                }
                if start >= 0 && size >= 0 {
                    for (name, (other_start, other_end, _)) in &allocated {
                        if *other_start >= 0
                            && *other_end > *other_start
                            && start < *other_end
                            && end > *other_start
                        {
                            errors.push(format!(
                                "New partition overlaps with existing region ({name})."
                            ));
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
                if !mount.is_empty()
                    && mount_assignments
                        .values()
                        .any(|assigned| assigned == &mount)
                {
                    errors.push(format!("Mount point {mount} is assigned more than once."));
                }
                let created_key = format!("new:{}", operation.index);
                allocated.insert(created_key.clone(), (start, end, fs));
                if table == "msdos" {
                    primary_count += 1;
                }
                if !mount.is_empty() {
                    mount_assignments.insert(created_key, mount);
                }
            }
            "delete" | "format" | "resize" | "set_mountpoint" => {
                let raw_partition = value_string(params, "partition");
                let partition = normalize_device_path(&raw_partition);
                let Some(partition) = partition else {
                    errors.push(format!(
                        "{}: partition does not belong to {}.",
                        operation.kind, journal.disk
                    ));
                    continue;
                };
                let Some((start, end, fs)) = allocated.get(&partition).cloned() else {
                    errors.push(format!(
                        "{}: {partition} is not present on {}.",
                        operation.kind, journal.disk
                    ));
                    continue;
                };
                let mut valid = true;
                if operation.kind == "resize" {
                    // Destructive shrink gate: GPT backup on external media,
                    // fresh NTFS clean-bit re-verification, AC power. Every
                    // refusal carries the cannot-be-undone warning. A grow
                    // (new size at or above the current size) cannot destroy
                    // data, so it skips the shrink attestations.
                    let new_size = value_i64(params, "new_size_bytes", -1);
                    let current_size = end.saturating_sub(start);
                    if new_size > 0 && (current_size <= 0 || new_size < current_size) {
                        errors.extend(validate_shrink_preconditions(&fs, params));
                    }
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
                            if name != &partition
                                && *other_start >= 0
                                && *other_end > *other_start
                                && start < *other_end
                                && new_end > *other_start
                            {
                                errors.push(format!("Resize partition: new size for {partition} would overlap with existing region ({name})."));
                                valid = false;
                                break;
                            }
                        }
                    }
                } else if operation.kind == "set_mountpoint" {
                    let mount = value_string(params, "mountpoint");
                    if mount == "/" && fs != "btrfs" {
                        errors
                            .push("Root partition (/) must use the Btrfs filesystem.".to_string());
                        valid = false;
                    }
                    if mount == "/boot/efi" && !matches!(fs.as_str(), "fat" | "fat32" | "vfat") {
                        errors.push("EFI System Partition (/boot/efi) must use FAT32.".to_string());
                        valid = false;
                    }
                    if !mount.is_empty()
                        && mount_assignments
                            .iter()
                            .any(|(assigned_partition, assigned)| {
                                assigned_partition != &partition && assigned == &mount
                            })
                    {
                        errors.push(format!("Mount point {mount} is assigned more than once."));
                        valid = false;
                    }
                    if valid {
                        if mount.is_empty() {
                            mount_assignments.remove(&partition);
                        } else {
                            mount_assignments.insert(partition.clone(), mount);
                        }
                    }
                }
                if valid {
                    match operation.kind.as_str() {
                        "delete" => {
                            allocated.remove(&partition);
                            mount_assignments.remove(&partition);
                            if table == "msdos" {
                                primary_count = primary_count.saturating_sub(1);
                            }
                        }
                        "resize" => {
                            let new_size = value_i64(params, "new_size_bytes", -1);
                            allocated
                                .insert(partition, (start, start.saturating_add(new_size), fs));
                        }
                        "format" => {
                            allocated.insert(
                                partition,
                                (
                                    start,
                                    end,
                                    value_string(params, "fs_type").to_ascii_lowercase(),
                                ),
                            );
                        }
                        _ => {}
                    }
                }
            }
            _ => errors.push(format!(
                "Unsupported partition operation: {}.",
                operation.kind
            )),
        }
    }

    let root_count = mount_assignments
        .values()
        .filter(|mount| mount.as_str() == "/")
        .count();
    if root_count == 0 {
        errors.push(
            "No root partition (/) configured. Mount at least one partition as '/' with Btrfs."
                .to_string(),
        );
    } else if root_count > 1 {
        errors.push("Exactly one root partition (/) must be configured.".to_string());
    }

    for part in current_parts
        .iter()
        .filter(|part| part.current || part.in_use)
    {
        for operation in &journal.ops {
            let partition = normalize_device_path(&value_string(&operation.params, "partition"));
            if partition.as_deref() != Some(part.name.as_str()) {
                continue;
            }
            if matches!(operation.kind.as_str(), "delete" | "format" | "resize") {
                errors.push(format!(
                    "Cannot modify {} — it is currently mounted or in use.",
                    part.name
                ));
                break;
            }
            if operation.kind == "set_mountpoint"
                && value_string(&operation.params, "mountpoint") == "/"
                && last_mountpoints.get(&value_string(&operation.params, "partition"))
                    == Some(&operation.index)
            {
                errors.push(format!(
                    "Cannot set {} as the root partition — it is currently mounted or in use.",
                    part.name
                ));
                break;
            }
        }
    }
    errors
}

const BIOS_BOOT_BYTES: u64 = 2 * 1024 * 1024;

fn emit_event(event: Value) -> Result<(), String> {
    println!(
        "{}",
        serde_json::to_string(&event).map_err(|error| error.to_string())?
    );
    std::io::stdout()
        .flush()
        .map_err(|error| format!("could not flush journal event: {error}"))
}

fn run_disk_operation(operation: installer_disk::DiskOperationInput) -> Result<(), String> {
    let backup_path = operation.backup_path().map(str::to_owned);
    let plan = installer_disk::build_plan(operation)?;
    let mut command = Command::new(&plan.argv[0]);
    command.args(&plan.argv[1..]);
    command.process_group(0);
    if plan.needs_confirmation {
        command.stdin(Stdio::piped());
    }
    let mut child = command
        .spawn()
        .map_err(|error| format!("could not execute disk operation: {error}"))?;
    if plan.needs_confirmation {
        if let Some(mut stdin) = child.stdin.take() {
            if let Err(error) = stdin.write_all(b"Yes\n") {
                crate::installer_stream::kill_process_group(&mut child);
                let _ = child.wait();
                return Err(format!("could not confirm disk operation: {error}"));
            }
        }
    }
    let started = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) => {}
            Err(error) => {
                crate::installer_stream::kill_process_group(&mut child);
                let _ = child.wait();
                return Err(format!("could not poll disk operation: {error}"));
            }
        }
        if started.elapsed() >= Duration::from_secs(plan.timeout_seconds) {
            crate::installer_stream::kill_process_group(&mut child);
            let _ = child.wait();
            return Err(format!(
                "disk operation timed out after {} seconds",
                plan.timeout_seconds
            ));
        }
        std::thread::sleep(Duration::from_millis(100));
    };
    if !status.success() {
        return Err(format!(
            "disk operation exited with {}",
            status
                .code()
                .map_or_else(|| "a signal".to_string(), |code| code.to_string())
        ));
    }
    if let Some(path) = backup_path {
        installer_disk::sync_backup(&path)?;
    }
    Ok(())
}

fn acquire_disk_lock(disk: &str) -> Result<File, String> {
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_CLOEXEC)
        .open(disk)
        .map_err(|error| format!("could not lock {disk} for exclusive use: {error}"))?;
    // The compatibility implementation permits this only for constrained
    // test environments. Production remains fail-closed when the lock cannot
    // be acquired.
    if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0
        && std::env::var("KYTH_INSTALL_ALLOW_NO_DISK_LOCK").as_deref() != Ok("1")
    {
        return Err(format!(
            "another process is using {disk}; close other installers and retry"
        ));
    }
    Ok(file)
}

fn runtime_lsblk(disk: &str) -> Result<Value, String> {
    let disk =
        normalize_device_path(disk).ok_or_else(|| "disk must be a safe device path".to_string())?;
    let output = Command::new("/usr/bin/lsblk")
        .args([
            "--json",
            "--bytes",
            "--paths",
            "--output",
            "NAME,SIZE,TYPE,FSTYPE,PARTTYPE,LABEL,MOUNTPOINT,MOUNTPOINTS,START,RO,PTTYPE",
            &disk,
        ])
        .output()
        .map_err(|error| format!("could not inspect {disk}: {error}"))?;
    if !output.status.success() {
        return Err(format!("lsblk could not inspect {disk}"));
    }
    serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("invalid lsblk snapshot for {disk}: {error}"))
}

fn runtime_partition_records(disk: &str) -> Result<Vec<PartitionRecord>, String> {
    let snapshot = runtime_lsblk(disk)?;
    installer_storage::parse_partitions(&snapshot.to_string())
}

fn runtime_disk_metadata(disk: &str) -> Result<(String, u64), String> {
    let disk =
        normalize_device_path(disk).ok_or_else(|| "disk must be a safe device path".to_string())?;
    let snapshot = runtime_lsblk(&disk)?;
    snapshot
        .get("blockdevices")
        .and_then(Value::as_array)
        .and_then(|entries| {
            entries.iter().find_map(|entry| {
                let name = entry
                    .get("name")
                    .and_then(Value::as_str)
                    .and_then(normalize_device_path)?;
                if name != disk || entry.get("type").and_then(Value::as_str) != Some("disk") {
                    return None;
                }
                Some((
                    entry
                        .get("pttype")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_ascii_lowercase(),
                    entry.get("size").and_then(Value::as_u64).unwrap_or(0),
                ))
            })
        })
        .ok_or_else(|| format!("lsblk did not return the selected disk {disk}"))
}

fn runtime_partitions() -> Result<HashMap<String, u32>, String> {
    let output = Command::new("/usr/bin/lsblk")
        .args([
            "--json",
            "--bytes",
            "--output",
            "NAME,TYPE,PARTN,START,SIZE",
        ])
        .output()
        .map_err(|error| format!("could not inspect partitions: {error}"))?;
    if !output.status.success() {
        return Err("lsblk could not inspect the partition table".to_string());
    }
    let value: Value = serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("invalid lsblk partition snapshot: {error}"))?;
    let mut result = HashMap::new();
    fn walk(value: &Value, result: &mut HashMap<String, u32>) {
        if let Some(entries) = value.get("blockdevices").and_then(Value::as_array) {
            for entry in entries {
                walk(entry, result);
            }
            return;
        }
        if value.get("type").and_then(Value::as_str) == Some("part") {
            if let (Some(name), Some(part_num)) = (
                value.get("name").and_then(Value::as_str),
                value.get("partn").and_then(Value::as_u64),
            ) {
                if let Some(name) = normalize_device_path(name) {
                    if let Ok(part_num) = u32::try_from(part_num) {
                        result.insert(name, part_num);
                    }
                }
            }
        }
        if let Some(children) = value.get("children").and_then(Value::as_array) {
            for child in children {
                walk(child, result);
            }
        }
    }
    walk(&value, &mut result);
    Ok(result)
}

fn find_new_partition(
    disk: &str,
    before: &HashMap<String, u32>,
    start: u64,
    size: u64,
) -> Result<String, String> {
    let disk =
        normalize_device_path(disk).ok_or_else(|| "disk must be a safe device path".to_string())?;
    let output = Command::new("/usr/bin/lsblk")
        .args([
            "--json",
            "--bytes",
            "--paths",
            "--output",
            "NAME,TYPE,START,SIZE",
            &disk,
        ])
        .output()
        .map_err(|error| format!("could not inspect created partition: {error}"))?;
    if !output.status.success() {
        return Err("lsblk could not find the created partition".to_string());
    }
    let value: Value = serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("invalid lsblk partition snapshot: {error}"))?;
    let mut candidates = Vec::new();
    fn walk(
        value: &Value,
        before: &HashMap<String, u32>,
        start: u64,
        size: u64,
        candidates: &mut Vec<String>,
    ) {
        if value.get("type").and_then(Value::as_str) == Some("part") {
            let name = value
                .get("name")
                .and_then(Value::as_str)
                .and_then(normalize_device_path);
            let start_bytes = value
                .get("start")
                .and_then(Value::as_u64)
                .unwrap_or(0)
                .saturating_mul(512);
            let actual_size = value.get("size").and_then(Value::as_u64).unwrap_or(0);
            if let Some(name) = name {
                if !before.contains_key(&name) && start_bytes == start && actual_size == size {
                    candidates.push(name);
                }
            }
        }
        if let Some(children) = value.get("children").and_then(Value::as_array) {
            for child in children {
                walk(child, before, start, size, candidates);
            }
        }
    }
    walk(&value, before, start, size, &mut candidates);
    candidates
        .into_iter()
        .next()
        .ok_or_else(|| "could not find the newly created partition".to_string())
}

fn value_u64(params: &Value, key: &str, default: u64) -> u64 {
    match params.get(key) {
        Some(Value::Number(value)) => value.as_u64().unwrap_or(default),
        Some(Value::String(value)) => value.parse::<u64>().unwrap_or(default),
        _ => default,
    }
}

fn part_num(partition: &str, parts: &HashMap<String, u32>) -> Result<u32, String> {
    let partition = normalize_device_path(partition)
        .ok_or_else(|| "partition must be a safe device path".to_string())?;
    parts
        .get(&partition)
        .copied()
        .ok_or_else(|| format!("partition {partition} was not found on the target disk"))
}

fn current_fs(partition: &str, current_parts: &[PartitionRecord]) -> Result<String, String> {
    let partition = normalize_device_path(partition)
        .ok_or_else(|| "partition must be a safe device path".to_string())?;
    current_parts
        .iter()
        .find(|part| part.name == partition)
        .map(|part| part.fstype.to_ascii_lowercase())
        .filter(|fstype| !fstype.is_empty())
        .ok_or_else(|| format!("filesystem type for {partition} is unavailable"))
}

fn shrink_filesystem(partition: &str, fs: &str, new_size: u64) -> Result<(), String> {
    match fs {
        "ntfs" | "ntfs3" => {
            for stage in ["check", "info", "dry_run", "resize"] {
                run_disk_operation(installer_disk::DiskOperationInput::FilesystemResize {
                    device: partition.to_string(),
                    fs: "ntfs".to_string(),
                    new_size_bytes: new_size,
                    stage: stage.to_string(),
                })?;
            }
        }
        "ext2" | "ext3" | "ext4" => {
            run_disk_operation(installer_disk::DiskOperationInput::FilesystemCheck {
                device: partition.to_string(),
            })?;
            run_disk_operation(installer_disk::DiskOperationInput::FilesystemResize {
                device: partition.to_string(),
                fs: "ext4".to_string(),
                new_size_bytes: new_size,
                stage: "resize".to_string(),
            })?;
        }
        "btrfs" => {
            let directory = tempfile::Builder::new()
                .prefix("kyth-btrfs-resize-")
                .tempdir()
                .map_err(|error| format!("could not create Btrfs resize mountpoint: {error}"))?;
            let mountpoint = directory.path().to_string_lossy().into_owned();
            run_disk_operation(installer_disk::DiskOperationInput::MountFilesystem {
                device: partition.to_string(),
                mountpoint: mountpoint.clone(),
                options: Vec::new(),
                bind: false,
            })?;
            let resize = run_disk_operation(installer_disk::DiskOperationInput::FilesystemResize {
                device: mountpoint.clone(),
                fs: "btrfs".to_string(),
                new_size_bytes: new_size,
                stage: "resize".to_string(),
            });
            let unmount =
                run_disk_operation(installer_disk::DiskOperationInput::UnmountFilesystem {
                    mountpoint,
                    recursive: false,
                    lazy: false,
                });
            resize.and(unmount)?;
        }
        _ => {
            return Err(format!(
                "Shrinking {fs} filesystems is not supported by this installer."
            ));
        }
    }
    Ok(())
}

fn execute_operation(
    operation: &mut PartitionOperation,
    journal: &PartitionJournal,
    current_parts: &[PartitionRecord],
    irreversible: &mut bool,
) -> Result<String, String> {
    let params = &mut operation.params;
    let target = value_string(params, "partition");
    let before = runtime_partitions()?;
    match operation.kind.as_str() {
        "new_table" => {
            let table_type = value_string(params, "table_type");
            run_disk_operation(installer_disk::DiskOperationInput::CreateLabel {
                disk: journal.disk.clone(),
                table_type: if table_type.is_empty() {
                    "gpt".to_string()
                } else {
                    table_type
                },
            })?;
            if value_string(params, "table_type").is_empty()
                || value_string(params, "table_type").eq_ignore_ascii_case("gpt")
            {
                let before_bios = runtime_partitions()?;
                run_disk_operation(
                    installer_disk::DiskOperationInput::CreateUnformattedPartition {
                        disk: journal.disk.clone(),
                        start: 1024 * 1024,
                        size: BIOS_BOOT_BYTES,
                        label: "biosboot".to_string(),
                        sector_size: 512,
                    },
                )?;
                let bios =
                    find_new_partition(&journal.disk, &before_bios, 1024 * 1024, BIOS_BOOT_BYTES)?;
                let number = part_num(&bios, &runtime_partitions()?)?;
                run_disk_operation(installer_disk::DiskOperationInput::SetPartitionFlag {
                    disk: journal.disk.clone(),
                    part_num: number,
                    flag: "bios_grub".to_string(),
                    enabled: true,
                })?;
            }
            Ok(journal.disk.clone())
        }
        "create" => {
            let start = value_u64(params, "start_bytes", 0);
            let size = value_u64(params, "size_bytes", 0);
            run_disk_operation(installer_disk::DiskOperationInput::CreatePartition {
                disk: journal.disk.clone(),
                start,
                size,
                fs: value_string(params, "fs_type"),
                label: value_string(params, "label"),
                sector_size: 512,
            })?;
            let created = find_new_partition(&journal.disk, &before, start, size)?;
            params["partition"] = Value::String(created.clone());
            params["_created_this_journal"] = Value::Bool(true);
            let fs = value_string(params, "fs_type");
            if fs != "linux-swap" {
                run_disk_operation(installer_disk::DiskOperationInput::FormatFilesystem {
                    device: created.clone(),
                    fs,
                    label: value_string(params, "label"),
                })?;
            }
            if value_string(params, "mountpoint") == "/boot/efi" {
                let number = part_num(&created, &runtime_partitions()?)?;
                run_disk_operation(installer_disk::DiskOperationInput::SetPartitionFlag {
                    disk: journal.disk.clone(),
                    part_num: number,
                    flag: "esp".to_string(),
                    enabled: true,
                })?;
            }
            Ok(created)
        }
        "delete" => {
            let number = part_num(&target, &before)?;
            run_disk_operation(installer_disk::DiskOperationInput::DeletePartition {
                disk: journal.disk.clone(),
                part_num: number,
            })?;
            Ok(target)
        }
        "resize" => {
            let number = part_num(&target, &before)?;
            let new_size = value_u64(params, "new_size_bytes", 0);
            let fs = current_fs(&target, current_parts)?;
            // A successful filesystem shrink cannot be undone by restoring
            // the old partition table. Mark this before starting the shrink
            // so a later resizepart failure also skips a harmful restore.
            *irreversible = true;
            shrink_filesystem(&target, &fs, new_size)?;
            run_disk_operation(installer_disk::DiskOperationInput::ResizePartition {
                disk: journal.disk.clone(),
                part_num: number,
                start: current_parts
                    .iter()
                    .find(|part| part.name == normalize_device_path(&target).unwrap_or_default())
                    .map(|part| part.start_bytes)
                    .unwrap_or(0),
                new_size,
                sector_size: 512,
            })?;
            Ok(target)
        }
        "format" => {
            let created_here = journal.ops.iter().any(|item| {
                item.kind == "create"
                    && item
                        .params
                        .get("_created_this_journal")
                        .and_then(Value::as_bool)
                        == Some(true)
                    && value_string(&item.params, "partition") == target
            });
            if !created_here {
                // Formatting an existing filesystem is irreversible even if
                // the utility exits non-zero after partially writing it.
                *irreversible = true;
            }
            run_disk_operation(installer_disk::DiskOperationInput::FormatFilesystem {
                device: target.clone(),
                fs: value_string(params, "fs_type"),
                label: value_string(params, "label"),
            })?;
            Ok(target)
        }
        "set_mountpoint" => Ok(target),
        _ => Err(format!("unsupported journal operation: {}", operation.kind)),
    }
}

fn root_partition(journal: &PartitionJournal) -> Option<String> {
    let mut assignments = HashMap::<String, String>::new();
    for operation in &journal.ops {
        match operation.kind.as_str() {
            "new_table" => assignments.clear(),
            "create" | "set_mountpoint" => {
                let partition =
                    normalize_device_path(&value_string(&operation.params, "partition"));
                let key = partition.unwrap_or_else(|| format!("new:{}", operation.index));
                let mountpoint = value_string(&operation.params, "mountpoint");
                if mountpoint.is_empty() {
                    assignments.remove(&key);
                } else {
                    assignments.insert(key, mountpoint);
                }
            }
            "delete" => {
                if let Some(partition) =
                    normalize_device_path(&value_string(&operation.params, "partition"))
                {
                    assignments.remove(&partition);
                }
            }
            _ => {}
        }
    }
    let roots: Vec<String> = assignments
        .into_iter()
        .filter_map(|(partition, mountpoint)| (mountpoint == "/").then_some(partition))
        .filter_map(|partition| normalize_device_path(&partition))
        .collect();
    (roots.len() == 1).then(|| roots[0].clone())
}

pub(crate) fn commit_request(input: JournalCommitInput) -> Result<Value, String> {
    commit_request_with_target_guard(input, crate::installer_guard::validate_target_disk)
}

fn commit_request_with_target_guard(
    mut input: JournalCommitInput,
    validate_target: impl FnOnce(&str) -> Result<(), String>,
) -> Result<Value, String> {
    // The partition editor has its own authenticated commit route, separate
    // from the guided installer phases. Repeat the protected/current-disk
    // check here, immediately before the first privileged disk probe or write.
    validate_target(&input.journal.disk)?;
    let _lock = acquire_disk_lock(&input.journal.disk)?;
    let current_parts = runtime_partition_records(&input.journal.disk)?;
    let (table_type, disk_size_bytes) = runtime_disk_metadata(&input.journal.disk)?;
    let errors = validate(&input.journal, &current_parts, &table_type, disk_size_bytes);
    if !errors.is_empty() {
        return Ok(serde_json::json!({"ok": false, "errors": errors}));
    }
    let directory = tempfile::Builder::new()
        .prefix("kyth-partition-")
        .tempdir()
        .map_err(|error| format!("could not create partition backup directory: {error}"))?;
    let backup_path = directory.path().join("partition-table.backup");
    let backup_path = backup_path.to_string_lossy().into_owned();
    run_disk_operation(installer_disk::DiskOperationInput::BackupTable {
        disk: input.journal.disk.clone(),
        backup_path: backup_path.clone(),
    })?;

    let mut irreversible = false;
    for index in 0..input.journal.ops.len() {
        if input.journal.ops[index].kind == "set_mountpoint" {
            continue;
        }
        let kind = input.journal.ops[index].kind.clone();
        let target = value_string(&input.journal.ops[index].params, "partition");
        emit_event(
            serde_json::json!({"event":"step","kind":kind,"status":"started","target":if target.is_empty() { input.journal.disk.clone() } else { target.clone() }}),
        )?;
        let journal_snapshot = input.journal.clone();
        match execute_operation(
            &mut input.journal.ops[index],
            &journal_snapshot,
            &current_parts,
            &mut irreversible,
        ) {
            Ok(completed_target) => {
                emit_event(
                    serde_json::json!({"event":"step","kind":kind,"status":"completed","target":completed_target}),
                )?;
            }
            Err(error) => {
                if !irreversible {
                    if let Err(restore_error) =
                        run_disk_operation(installer_disk::DiskOperationInput::RestoreTable {
                            disk: input.journal.disk.clone(),
                            backup_path: backup_path.clone(),
                        })
                    {
                        input.journal.irreversible_completed = true;
                        return Ok(serde_json::json!({
                            "ok": false,
                            "irreversible": true,
                            "recovery_required": true,
                            "message": format!("{error}; partition-table rollback also failed: {restore_error}"),
                            "journal": input.journal,
                        }));
                    }
                }
                input.journal.irreversible_completed = irreversible;
                return Ok(serde_json::json!({
                    "ok": false,
                    "irreversible": irreversible,
                    "message": error,
                    "journal": input.journal,
                }));
            }
        }
    }
    input.journal.irreversible_completed = irreversible;
    input.journal.root_partition = root_partition(&input.journal);
    input.journal.committed = true;
    Ok(serde_json::json!({
        "ok": true,
        "root_partition": input.journal.root_partition,
        "journal": input.journal,
    }))
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

    fn resize_journal(partition: &str, params: serde_json::Value) -> PartitionJournal {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        let mut full = params;
        full["partition"] = serde_json::Value::String(partition.to_string());
        journal.add_op("resize", full);
        // A btrfs root elsewhere so validation reaches the shrink gate
        // instead of stopping at "no root partition".
        journal.add_op(
            "create",
            json!({
                "partition": "/dev/sda9",
                "start_bytes": 96_i64 * 1024 * 1024 * 1024,
                "size_bytes": 31_i64 * 1024 * 1024 * 1024,
                "fs_type": "btrfs",
                "mountpoint": "/",
            }),
        );
        journal
    }

    #[test]
    fn shrink_commits_require_gpt_backup_ac_and_ntfs_reverification() {
        let parts = vec![partition("/dev/sda2", "ntfs", false)];
        // Bare shrink: refused on all three attestations, every refusal
        // saying the operation cannot be undone.
        let journal = resize_journal(
            "/dev/sda2",
            json!({"new_size_bytes": 32_i64 * 1024 * 1024 * 1024}),
        );
        let errors = validate(&journal, &parts, "gpt", 128 * 1024 * 1024 * 1024);
        assert!(
            errors
                .iter()
                .any(|error| error.contains("GPT backup file path is required")),
            "{errors:?}"
        );
        assert!(
            errors
                .iter()
                .any(|error| error.contains("dirty bit must be re-verified")),
            "{errors:?}"
        );
        assert!(
            errors
                .iter()
                .any(|error| error.contains("AC power must be confirmed")),
            "{errors:?}"
        );
        assert!(
            errors
                .iter()
                .all(|error| error.contains("cannot be undone")),
            "{errors:?}"
        );
        // Same-disk GPT backup path is refused: it dies with the disk.
        let journal = resize_journal(
            "/dev/sda2",
            json!({"new_size_bytes": 32_i64 * 1024 * 1024 * 1024, "gpt_backup_path": "/root/gpt.bak", "ntfs_verified_clean": true, "on_ac_power": true}),
        );
        let errors = validate(&journal, &parts, "gpt", 128 * 1024 * 1024 * 1024);
        assert!(
            errors.iter().any(|error| error.contains("external media")),
            "{errors:?}"
        );
        // Fully attested shrink passes the gate.
        let journal = resize_journal(
            "/dev/sda2",
            json!({"new_size_bytes": 32_i64 * 1024 * 1024 * 1024, "gpt_backup_path": "/run/media/alice/BACKUP/sda-gpt.bak", "ntfs_verified_clean": true, "on_ac_power": true}),
        );
        let errors = validate(&journal, &parts, "gpt", 128 * 1024 * 1024 * 1024);
        assert!(errors.is_empty(), "{errors:?}");
        // Non-NTFS shrink needs no clean-bit attestation, but still needs
        // the backup and AC power.
        let ext4 = vec![partition("/dev/sda2", "ext4", false)];
        let journal = resize_journal(
            "/dev/sda2",
            json!({"new_size_bytes": 32_i64 * 1024 * 1024 * 1024, "gpt_backup_path": "/mnt/usb/sda-gpt.bak", "on_ac_power": true}),
        );
        let errors = validate(&journal, &ext4, "gpt", 128 * 1024 * 1024 * 1024);
        assert!(errors.is_empty(), "{errors:?}");
        // A grow (new size above current) destroys nothing, so it skips the
        // shrink attestations entirely: 64 GiB -> 80 GiB with no backup, no
        // NTFS flag, no AC attestation must not raise the shrink gate.
        let journal = resize_journal(
            "/dev/sda2",
            json!({"new_size_bytes": 80_i64 * 1024 * 1024 * 1024}),
        );
        let errors = validate(&journal, &ext4, "gpt", 128 * 1024 * 1024 * 1024);
        assert!(errors.is_empty(), "{errors:?}");
    }

    #[test]
    fn external_media_paths_are_absolute_and_escapeless() {
        assert!(path_on_external_media(
            "/run/media/alice/BACKUP/sda-gpt.bak"
        ));
        assert!(path_on_external_media("/mnt/usb/sda-gpt.bak"));
        assert!(!path_on_external_media("/root/gpt.bak"));
        assert!(!path_on_external_media("run/media/alice/x"));
        assert!(!path_on_external_media("/run/media/../etc/shadow"));
        assert!(!path_on_external_media(""));
    }

    #[test]
    fn creates_a_normalized_empty_journal() {
        let journal = PartitionJournal::new("sda").expect("valid disk path");
        assert_eq!(journal.disk, "/dev/sda");
        assert!(journal.ops.is_empty());
        assert!(!journal.committed);
    }

    #[test]
    fn partition_commit_rejects_protected_target_before_disk_access() {
        let journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        let mut journal = journal;
        journal.add_op("new_table", json!({"table_type": "gpt"}));
        let error = commit_request_with_target_guard(JournalCommitInput { journal }, |disk| {
            assert_eq!(disk, "/dev/sda");
            Err("selected disk is the current live-session disk".to_string())
        })
        .unwrap_err();
        assert!(error.contains("current live-session disk"));
    }

    #[test]
    fn stages_and_removes_operations_without_rewriting_identity() {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        assert_eq!(journal.add_op("create", json!({"mountpoint": "/"})), 0);
        assert_eq!(
            journal.add_op("set_mountpoint", json!({"mountpoint": "/home"})),
            1
        );
        assert!(journal.remove_op(0));
        assert_eq!(journal.pending()[0].index, 1);
        assert_eq!(journal.add_op("format", json!({"fs_type": "btrfs"})), 2);
        assert!(!journal.remove_op(99));
    }

    #[test]
    fn removed_operation_ids_are_not_reused() {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        journal.add_op("create", json!({}));
        journal.add_op("format", json!({}));
        assert!(journal.remove_op(0));
        let next = journal.add_op("delete", json!({}));
        assert_eq!(next, 2);
        assert_eq!(
            journal.ops.iter().map(|op| op.index).collect::<Vec<_>>(),
            [1, 2]
        );
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
    fn target_validation_rejects_a_partition_from_another_disk() {
        let invalid = validate_target_request(JournalTargetInput {
            disk: "/dev/sda".to_string(),
            partition: "/dev/sdb3".to_string(),
        });
        assert_eq!(invalid["valid"], false);
        assert!(invalid["error"]
            .as_str()
            .unwrap()
            .contains("does not belong"));
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
        assert!(manual_mounts(&journal, &[])
            .expect("root mounts are skipped")
            .is_empty());

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
    fn manual_mount_projection_uses_last_assignment_and_ignores_deleted_partitions() {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        journal.add_op(
            "set_mountpoint",
            json!({"partition": "/dev/sda2", "mountpoint": "/old"}),
        );
        journal.add_op(
            "set_mountpoint",
            json!({"partition": "/dev/sda2", "mountpoint": "/home"}),
        );
        journal.add_op(
            "set_mountpoint",
            json!({"partition": "/dev/sda3", "mountpoint": "/scratch"}),
        );
        journal.add_op("delete", json!({"partition": "/dev/sda3"}));
        journal.mark_committed(None).expect("commit metadata");

        let mounts = manual_mounts(
            &journal,
            &[
                partition("/dev/sda2", "ext4", false),
                partition("/dev/sda3", "xfs", false),
            ],
        )
        .expect("final mount projection");
        assert_eq!(mounts.len(), 1);
        assert_eq!(mounts[0].mountpoint, "/home");
        assert_eq!(mounts[0].partition, "/dev/sda2");
    }

    #[test]
    fn validates_a_single_btrfs_root_assignment() {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        journal.add_op(
            "set_mountpoint",
            json!({"partition": "/dev/sda2", "mountpoint": "/"}),
        );
        let errors = validate(
            &journal,
            &[partition("/dev/sda2", "btrfs", false)],
            "gpt",
            200 * 1024 * 1024 * 1024,
        );
        assert!(errors.is_empty(), "unexpected journal errors: {errors:?}");
    }

    #[test]
    fn rejects_root_partition_deleted_later_in_the_same_journal() {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        journal.add_op(
            "set_mountpoint",
            json!({"partition": "/dev/sda2", "mountpoint": "/"}),
        );
        journal.add_op("delete", json!({"partition": "/dev/sda2"}));
        let errors = validate(
            &journal,
            &[partition("/dev/sda2", "btrfs", false)],
            "gpt",
            128 * 1024 * 1024 * 1024,
        );
        assert!(
            errors
                .iter()
                .any(|error| error.contains("No root partition")),
            "{errors:?}"
        );
    }

    #[test]
    fn committed_root_projection_does_not_return_a_deleted_root() {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        journal.add_op(
            "create",
            json!({"partition": "/dev/sda2", "mountpoint": "/", "fs_type": "btrfs"}),
        );
        journal.add_op("delete", json!({"partition": "/dev/sda2"}));
        assert_eq!(root_partition(&journal), None);
    }

    #[test]
    fn rejects_zero_sized_and_out_of_bounds_created_partitions() {
        for (start, size, expected) in [
            (2 * 1024 * 1024_i64, 0_i64, "invalid start or size"),
            (
                2 * 1024 * 1024_i64,
                200 * 1024 * 1024 * 1024_i64,
                "extends past the end",
            ),
            (
                2 * 1024 * 1024_i64 + 1,
                64 * 1024 * 1024 * 1024_i64,
                "align to 512-byte",
            ),
        ] {
            let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
            journal.add_op("create", json!({"start_bytes": start, "size_bytes": size, "fs_type": "btrfs", "mountpoint": "/"}));
            let errors = validate(&journal, &[], "gpt", 128 * 1024 * 1024 * 1024);
            assert!(
                errors.iter().any(|error| error.contains(expected)),
                "{expected}: {errors:?}"
            );
        }
    }

    #[test]
    fn rejects_unknown_journal_operations_during_validation() {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        journal.add_op("erase_magic", json!({}));
        let errors = validate(&journal, &[], "gpt", 128 * 1024 * 1024 * 1024);
        assert!(
            errors
                .iter()
                .any(|error| error.contains("Unsupported partition operation")),
            "{errors:?}"
        );
    }

    #[test]
    fn recognizes_lsblk_dos_table_name_for_primary_partition_limit() {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        journal.add_op("create", json!({"start_bytes": 100 * 1024 * 1024_i64, "size_bytes": 1024 * 1024_i64, "fs_type": "btrfs", "mountpoint": "/"}));
        let parts = (1..=4)
            .map(|index| partition(&format!("/dev/sda{index}"), "ext4", false))
            .collect::<Vec<_>>();
        let errors = validate(&journal, &parts, "dos", 128 * 1024 * 1024 * 1024);
        assert!(
            errors
                .iter()
                .any(|error| error.contains("at most 4 primary partitions")),
            "{errors:?}"
        );
    }

    #[test]
    fn rejects_duplicate_roots_overlaps_and_in_use_partitions() {
        let mut journal = PartitionJournal::new("/dev/sda").expect("valid disk path");
        journal.add_op(
            "set_mountpoint",
            json!({"partition": "/dev/sda2", "mountpoint": "/"}),
        );
        journal.add_op(
            "set_mountpoint",
            json!({"partition": "/dev/sda3", "mountpoint": "/"}),
        );
        journal.add_op("create", json!({"start_bytes": 2 * 1024 * 1024_u64, "size_bytes": 64_u64 * 1024 * 1024 * 1024, "fs_type": "btrfs", "mountpoint": "/home"}));
        journal.add_op(
            "format",
            json!({"partition": "/dev/sda2", "fs_type": "btrfs"}),
        );
        let errors = validate(
            &journal,
            &[
                partition("/dev/sda2", "btrfs", true),
                partition("/dev/sda3", "btrfs", false),
            ],
            "gpt",
            200 * 1024 * 1024 * 1024,
        );
        assert!(errors
            .iter()
            .any(|error| error.contains("assigned more than once")));
        assert!(errors.iter().any(|error| error.contains("overlaps")));
        assert!(errors
            .iter()
            .any(|error| error.contains("Cannot set /dev/sda2")));
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
            let errors = validate(
                &journal,
                &case.partitions,
                &case.table_type,
                case.disk_size_bytes,
            );
            for expected in case.expected_errors {
                assert!(
                    errors.iter().any(|error| error.contains(&expected)),
                    "{}: {errors:?}",
                    case.name
                );
            }
            if case.name == "single-btrfs-root" {
                assert!(errors.is_empty(), "{}: {errors:?}", case.name);
            }
        }
    }
}
