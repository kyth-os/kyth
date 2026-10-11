//! Durable crash-recovery journal for the native installer.
//!
//! The executor records every destructive operation here as started/completed
//! with wall-clock timestamps and fsyncs after every write, so a crash and
//! retry — or a Rescue boot classifying an interrupted install — can tell
//! which mutations already happened.
//!
//! The journal lives at `<esp>/.kyth-install-journal.json` when the ESP is
//! already mounted, otherwise at `<target_root>/.kyth-install-journal.json`.
//! It is append-only across retries: opening an existing journal keeps its
//! records, and a corrupt journal fails closed rather than being reset.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::OpenOptionsExt;
use std::path::{Component, Path, PathBuf};

/// Journal file name, fixed so Rescue tooling can find it without parsing
/// installer state.
pub const JOURNAL_FILE_NAME: &str = ".kyth-install-journal.json";

const SCHEMA_VERSION: u64 = 1;
const MAX_JOURNAL_BYTES: u64 = 1024 * 1024;

/// Lifecycle of one recorded operation.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum OpState {
    Started,
    Completed,
}

/// One recorded operation: when it started and, if it finished, when it
/// completed. A record with `completed == None` means the operation was
/// interrupted (crash, power loss, cancellation) before it finished.
#[derive(Clone, Debug)]
pub struct JournalOp {
    pub name: String,
    pub started: u64,
    pub completed: Option<u64>,
}

/// The full journal contents, as returned by [`DurableJournal::load`] for
/// Rescue-boot classification.
#[derive(Clone, Debug, Default)]
pub struct JournalState {
    pub ops: Vec<JournalOp>,
}

impl JournalState {
    /// True when `name` was recorded and at least one record completed.
    pub fn completed(&self, name: &str) -> bool {
        self.ops
            .iter()
            .any(|op| op.name == name && op.completed.is_some())
    }

    /// True when `name` was ever recorded, completed or not.
    pub fn started(&self, name: &str) -> bool {
        self.ops.iter().any(|op| op.name == name)
    }
}

/// Append-only handle to the on-disk journal. Every mutation is written
/// atomically (temp file + rename) and fsync'd, including the directory.
///
/// FAT32 (the ESP) offers no atomic-rename guarantee: a crash or power loss
/// mid-rename can leave a torn or vanished journal behind. Every write is
/// therefore verified by reading the file back and checking it parses with
/// the expected record count; a mismatch retries once, then fails closed
/// rather than continuing with untrustworthy crash-recovery state. A journal
/// that cannot be loaded — corrupt or vanished — is never silently reset to
/// empty: without trustworthy records a retry cannot know what already
/// happened.
pub struct DurableJournal {
    path: PathBuf,
}

fn unix_now() -> Result<u64, String> {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .map_err(|error| format!("could not determine journal timestamp: {error}"))
}

fn validated_op_name(op: &str) -> Result<String, String> {
    let name = op.trim();
    if name.is_empty() || name.len() > 64 {
        return Err("journal operation name must be 1-64 characters".to_string());
    }
    if !name
        .bytes()
        .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_')
    {
        return Err(format!(
            "journal operation name is not a safe identifier: {name:?}"
        ));
    }
    Ok(name.to_string())
}

fn safe_directory(dir: &Path, label: &str) -> Result<(), String> {
    if !dir.is_absolute()
        || dir
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return Err(format!(
            "{label} must be an absolute path without parent traversal"
        ));
    }
    Ok(())
}

impl DurableJournal {
    /// Open (or create) the journal. When `esp_mount` is given the journal
    /// lives at `<esp>/.kyth-install-journal.json`, otherwise at
    /// `<target_root>/.kyth-install-journal.json`. An existing journal is
    /// kept as-is so retries see earlier records; a corrupt one fails
    /// closed.
    pub fn open(esp_mount: Option<&Path>, target_root: &Path) -> Result<Self, String> {
        let dir = esp_mount.unwrap_or(target_root);
        safe_directory(dir, "journal directory")?;
        fs::create_dir_all(dir).map_err(|error| {
            format!(
                "could not create journal directory {}: {error}",
                dir.display()
            )
        })?;
        let metadata = fs::symlink_metadata(dir).map_err(|error| {
            format!(
                "could not inspect journal directory {}: {error}",
                dir.display()
            )
        })?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err(format!(
                "journal directory is not a real directory: {}",
                dir.display()
            ));
        }
        let journal = Self {
            path: dir.join(JOURNAL_FILE_NAME),
        };
        match fs::symlink_metadata(&journal.path) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                journal.write_state(&JournalState::default())?;
            }
            Ok(metadata) => {
                if metadata.file_type().is_symlink() || !metadata.is_file() {
                    return Err(format!(
                        "journal path is not a regular file: {}",
                        journal.path.display()
                    ));
                }
                // Fail closed on a corrupt journal: without trustworthy
                // records a retry cannot know what already happened.
                Self::load(&journal.path)?;
            }
            Err(error) => {
                return Err(format!(
                    "could not inspect journal {}: {error}",
                    journal.path.display()
                ));
            }
        }
        Ok(journal)
    }

    /// Absolute path of the journal file.
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Record an operation transition, fsync'd before returning. `Started`
    /// appends a new record; `Completed` closes the most recent open record
    /// with that name (or records a standalone completed entry when none is
    /// open). Fails closed when the journal cannot be loaded: a journal that
    /// vanished after open() is never silently reset to empty, which would
    /// lose the crash-recovery history a retry depends on.
    pub fn record(&self, op: &str, state: OpState) -> Result<(), String> {
        let name = validated_op_name(op)?;
        let now = unix_now()?;
        let mut journal = Self::load(&self.path)?;
        match state {
            OpState::Started => journal.ops.push(JournalOp {
                name,
                started: now,
                completed: None,
            }),
            OpState::Completed => {
                if let Some(record) = journal
                    .ops
                    .iter_mut()
                    .rev()
                    .find(|record| record.name == name && record.completed.is_none())
                {
                    record.completed = Some(now);
                } else {
                    journal.ops.push(JournalOp {
                        name,
                        started: now,
                        completed: Some(now),
                    });
                }
            }
        }
        self.write_state(&journal)
    }

    /// Append-only union merge of two journal states. For each operation
    /// name, a `Completed` record wins over `Started`/absent; a destination
    /// record is never downgraded or dropped. Staging records keep their
    /// original order; a destination record survives unless the staging
    /// journal already completed that operation.
    fn merge_journal_states(staging: JournalState, existing: JournalState) -> JournalState {
        let mut merged = staging.ops;
        for op in existing.ops {
            if merged
                .iter()
                .any(|staged| staged.name == op.name && staged.completed.is_some())
            {
                continue;
            }
            merged.push(op);
        }
        JournalState { ops: merged }
    }

    /// Atomically move this journal's records to `dest` (fsync'd) and
    /// return a handle to the copy. Used to relocate the journal onto the
    /// ESP before a destructive step without losing earlier records.
    ///
    /// Merge semantics: when a journal already exists at `dest`, its records
    /// are union-merged with this journal's before writing — `Completed`
    /// wins over `Started`/absent, and records are never downgraded or
    /// dropped. A retry that opens a fresh staging journal must not delete
    /// completions a previous run recorded (e.g. `ntfs_shrink`), or the
    /// operation would run a second time.
    ///
    /// A corrupt or unparseable destination journal fails toward the fresh
    /// staging records: they are kept and written, and a warning is
    /// logged — never silently discarded.
    pub fn relocate(&self, dest: &Path) -> Result<Self, String> {
        if dest == self.path.as_path() {
            return Ok(Self {
                path: self.path.clone(),
            });
        }
        let parent = dest
            .parent()
            .ok_or_else(|| "journal destination has no parent directory".to_string())?;
        safe_directory(parent, "journal destination directory")?;
        fs::create_dir_all(parent).map_err(|error| {
            format!(
                "could not create journal destination {}: {error}",
                parent.display()
            )
        })?;
        let staging = Self::load(&self.path)?;
        let merged = match fs::symlink_metadata(dest) {
            Ok(_) => match Self::load(dest) {
                Ok(existing) => Self::merge_journal_states(staging, existing),
                Err(error) => {
                    eprintln!(
                        "install journal destination {} is corrupt ({}); keeping fresh staging records",
                        dest.display(),
                        error
                    );
                    staging
                }
            },
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => staging,
            Err(error) => {
                return Err(format!(
                    "could not inspect journal destination {}: {error}",
                    dest.display()
                ))
            }
        };
        let relocated = Self {
            path: dest.to_path_buf(),
        };
        relocated.write_state(&merged)?;
        Ok(relocated)
    }

    /// Load the journal at `path` for Rescue-boot classification. Fails
    /// closed on missing or corrupt files.
    pub fn load(path: &Path) -> Result<JournalState, String> {
        let raw = read_regular_file(path)?;
        let value: serde_json::Value = serde_json::from_slice(&raw)
            .map_err(|error| format!("install journal is invalid: {error}"))?;
        if value.get("schema_version").and_then(|v| v.as_u64()) != Some(SCHEMA_VERSION) {
            return Err("install journal has an unsupported schema".to_string());
        }
        let mut ops = Vec::new();
        for entry in value
            .get("ops")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default()
        {
            let name = entry
                .get("name")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "install journal entry has no name".to_string())?;
            let name = validated_op_name(name)?;
            let started = entry
                .get("started")
                .and_then(|v| v.as_u64())
                .ok_or_else(|| format!("install journal entry {name:?} has no start timestamp"))?;
            let completed = entry.get("completed").and_then(|v| v.as_u64());
            ops.push(JournalOp {
                name,
                started,
                completed,
            });
        }
        Ok(JournalState { ops })
    }

    fn write_state(&self, state: &JournalState) -> Result<(), String> {
        let mut ops = Vec::with_capacity(state.ops.len());
        for op in &state.ops {
            ops.push(serde_json::json!({
                "name": op.name,
                "started": op.started,
                "completed": op.completed,
            }));
        }
        let document = serde_json::json!({
            "schema_version": SCHEMA_VERSION,
            "ops": ops,
        });
        let bytes = serde_json::to_vec(&document)
            .map_err(|error| format!("could not encode install journal: {error}"))?;
        let expected_records = state.ops.len();
        write_atomically(&self.path, &bytes)?;
        if Self::load(&self.path).is_ok_and(|reloaded| reloaded.ops.len() == expected_records) {
            return Ok(());
        }
        // Read-back mismatch: a torn rename on FAT32 can leave a partial or
        // vanished file. Retry once, then fail closed rather than continue
        // with untrustworthy crash-recovery state.
        write_atomically(&self.path, &bytes)?;
        let reloaded = Self::load(&self.path)
            .map_err(|error| format!("install journal failed verification after write: {error}"))?;
        if reloaded.ops.len() == expected_records {
            Ok(())
        } else {
            Err(format!(
                "install journal record count mismatch after write: expected {expected_records}, found {}",
                reloaded.ops.len()
            ))
        }
    }
}

fn read_regular_file(path: &Path) -> Result<Vec<u8>, String> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| format!("could not inspect {}: {error}", path.display()))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(format!(
            "{} is missing or not a regular file",
            path.display()
        ));
    }
    if metadata.len() > MAX_JOURNAL_BYTES {
        return Err(format!(
            "{} is too large to be an install journal",
            path.display()
        ));
    }
    fs::read(path).map_err(|error| format!("could not read {}: {error}", path.display()))
}

/// Write `bytes` to `path` atomically: temp file in the same directory,
/// fsync the file, rename over the target, fsync the directory. A crash
/// leaves the old journal or the new one, never a torn write.
fn write_atomically(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let parent = path
        .parent()
        .ok_or_else(|| "journal path has no parent directory".to_string())?;
    safe_directory(parent, "journal directory")?;
    let temporary = path.with_extension("json.tmp");
    let _ = fs::remove_file(&temporary);
    let result = (|| {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o644)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&temporary)
            .map_err(|error| format!("could not create temporary journal: {error}"))?;
        file.write_all(bytes)
            .map_err(|error| format!("could not write journal: {error}"))?;
        file.sync_all()
            .map_err(|error| format!("could not sync journal: {error}"))?;
        drop(file);
        fs::rename(&temporary, path)
            .map_err(|error| format!("could not replace journal: {error}"))?;
        OpenOptions::new()
            .read(true)
            .open(parent)
            .and_then(|directory| directory.sync_all())
            .map_err(|error| format!("could not sync journal directory: {error}"))
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tempdir() -> tempfile::TempDir {
        tempfile::tempdir().expect("temporary journal directory")
    }

    #[test]
    fn records_started_and_completed_with_fsync() {
        let dir = tempdir();
        let journal = DurableJournal::open(None, dir.path()).expect("journal should open");
        assert_eq!(journal.path(), dir.path().join(JOURNAL_FILE_NAME).as_path());
        journal
            .record("ntfs_shrink", OpState::Started)
            .expect("started should record");
        let state = DurableJournal::load(journal.path()).expect("journal should load");
        assert!(state.started("ntfs_shrink"));
        assert!(!state.completed("ntfs_shrink"));
        journal
            .record("ntfs_shrink", OpState::Completed)
            .expect("completed should record");
        let state = DurableJournal::load(journal.path()).expect("journal should load");
        assert!(state.completed("ntfs_shrink"));
        assert_eq!(state.ops.len(), 1);
        assert!(state.ops[0].completed.unwrap() >= state.ops[0].started);
    }

    #[test]
    fn journal_file_matches_documented_shape() {
        let dir = tempdir();
        let journal = DurableJournal::open(None, dir.path()).expect("journal should open");
        journal
            .record("image_write", OpState::Started)
            .expect("started should record");
        let raw = fs::read_to_string(journal.path()).expect("journal file should exist");
        let value: serde_json::Value =
            serde_json::from_str(&raw).expect("journal file should be JSON");
        assert_eq!(value["schema_version"], 1);
        let ops = value["ops"].as_array().expect("ops should be an array");
        assert_eq!(ops.len(), 1);
        assert_eq!(ops[0]["name"], "image_write");
        assert!(ops[0]["started"].as_u64().is_some());
        assert!(ops[0]["completed"].is_null());
    }

    #[test]
    fn esp_mount_selects_esp_journal_path() {
        let dir = tempdir();
        let esp = dir.path().join("esp");
        let journal = DurableJournal::open(Some(esp.as_path()), dir.path())
            .expect("journal should open on the ESP");
        assert_eq!(journal.path(), esp.join(JOURNAL_FILE_NAME).as_path());
    }

    #[test]
    fn reopening_keeps_earlier_records_for_retries() {
        let dir = tempdir();
        let first = DurableJournal::open(None, dir.path()).expect("journal should open");
        first
            .record("partition_table", OpState::Completed)
            .expect("record should persist");
        drop(first);
        let second = DurableJournal::open(None, dir.path()).expect("journal should reopen");
        let state = DurableJournal::load(second.path()).expect("journal should load");
        assert!(state.completed("partition_table"));
        second
            .record("ntfs_shrink", OpState::Started)
            .expect("record should persist");
        let state = DurableJournal::load(second.path()).expect("journal should load");
        assert_eq!(state.ops.len(), 2);
    }

    #[test]
    fn corrupt_journal_fails_closed_on_open_and_load() {
        let dir = tempdir();
        let journal = DurableJournal::open(None, dir.path()).expect("journal should open");
        fs::write(journal.path(), "{not json").expect("corrupt fixture should write");
        assert!(DurableJournal::load(journal.path()).is_err());
        assert!(DurableJournal::open(None, dir.path()).is_err());
    }

    #[test]
    fn relocate_carries_records_to_the_new_path() {
        let dir = tempdir();
        let journal = DurableJournal::open(None, dir.path()).expect("journal should open");
        journal
            .record("partition_table", OpState::Started)
            .expect("record should persist");
        let esp = dir.path().join("esp");
        fs::create_dir_all(&esp).expect("esp fixture should exist");
        let dest = esp.join(JOURNAL_FILE_NAME);
        let moved = journal.relocate(&dest).expect("relocate should succeed");
        assert_eq!(moved.path(), dest.as_path());
        let state = DurableJournal::load(&dest).expect("relocated journal should load");
        assert!(state.started("partition_table"));
        moved
            .record("partition_table", OpState::Completed)
            .expect("record should persist on the copy");
        assert!(DurableJournal::load(&dest)
            .unwrap()
            .completed("partition_table"));
    }

    #[test]
    fn record_fails_closed_when_journal_vanishes_after_open() {
        let dir = tempdir();
        let journal = DurableJournal::open(None, dir.path()).expect("journal should open");
        journal
            .record("image_write", OpState::Started)
            .expect("record should persist");
        // A torn FAT32 rename (or an unmounted ESP) can make the journal
        // vanish between writes: recording must fail closed, never silently
        // reset to empty and lose the crash-recovery history.
        fs::remove_file(journal.path()).expect("journal file should delete");
        assert!(
            journal.record("image_write", OpState::Completed).is_err(),
            "a vanished journal must not silently reset to empty"
        );
    }

    #[test]
    fn rejects_unsafe_operation_names_and_paths() {
        let dir = tempdir();
        let journal = DurableJournal::open(None, dir.path()).expect("journal should open");
        for bad in ["", "has space", "UPPER", "semi;colon", "../escape"] {
            assert!(
                journal.record(bad, OpState::Started).is_err(),
                "{bad:?} should be rejected"
            );
        }
        assert!(DurableJournal::open(None, Path::new("relative/path")).is_err());
    }

    #[test]
    fn relocate_merges_instead_of_deleting_completed_records() {
        let dir = tempdir();
        let staging_dir = dir.path().join("staging");
        let esp = dir.path().join("esp");
        // Run 1: the ESP journal records ntfs_shrink as completed.
        let first =
            DurableJournal::open(Some(esp.as_path()), dir.path()).expect("ESP journal should open");
        first
            .record("ntfs_shrink", OpState::Completed)
            .expect("record should persist");
        // Run 2: a fresh staging journal knows nothing about the shrink.
        let staging =
            DurableJournal::open(None, staging_dir.as_path()).expect("staging journal should open");
        staging
            .record("partition_table", OpState::Started)
            .expect("record should persist");
        // Relocating the fresh staging journal must NOT delete the
        // completion record — that is what a retry does via
        // ensure_esp_journal before destructive steps.
        let dest = esp.join(JOURNAL_FILE_NAME);
        let relocated = staging.relocate(&dest).expect("relocate should merge");
        let state = DurableJournal::load(relocated.path()).expect("journal should load");
        assert!(
            state.completed("ntfs_shrink"),
            "relocate must preserve the run-1 completion: {state:?}"
        );
        assert!(state.started("partition_table"));
        assert!(
            !state.completed("partition_table"),
            "staging records keep their own state: {state:?}"
        );
    }

    #[test]
    fn relocate_keeps_staging_records_when_destination_is_corrupt() {
        let dir = tempdir();
        let staging_dir = dir.path().join("staging");
        let esp = dir.path().join("esp");
        fs::create_dir_all(&esp).expect("esp fixture should exist");
        let dest = esp.join(JOURNAL_FILE_NAME);
        fs::write(&dest, "{not json").expect("corrupt destination fixture should write");
        let staging =
            DurableJournal::open(None, staging_dir.as_path()).expect("staging journal should open");
        staging
            .record("ntfs_shrink", OpState::Started)
            .expect("record should persist");
        // A corrupt destination fails toward the fresh staging state: the
        // staging records are kept and written, not discarded.
        let relocated = staging
            .relocate(&dest)
            .expect("relocate should keep staging records on corrupt destination");
        let state = DurableJournal::load(relocated.path()).expect("journal should load");
        assert!(state.started("ntfs_shrink"));
        assert_eq!(state.ops.len(), 1);
    }
}
