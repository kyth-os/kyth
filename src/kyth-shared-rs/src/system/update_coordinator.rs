//! Locked atomic coordinator for boot-health/staged-update state.
//!
//! This ports the synchronization primitive from `update_coordinator.py`.
//! Callers still decide which state transition is valid; the coordinator only
//! guarantees that a read/transform/write transaction cannot lose a concurrent
//! update.

use super::boot_health::{read_state, BootHealthState};
use rustix::fs::{flock, FlockOperation};
use std::fs::OpenOptions;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
pub struct UpdateCoordinator { path: PathBuf }

impl UpdateCoordinator {
    pub fn new(path: impl AsRef<Path>) -> Self { Self { path: path.as_ref().to_path_buf() } }

    pub fn read(&self) -> BootHealthState { read_state(&self.path) }

    pub fn transaction<F>(&self, transform: F) -> std::io::Result<BootHealthState>
    where F: FnOnce(BootHealthState) -> BootHealthState {
        if let Some(parent) = self.path.parent() { std::fs::create_dir_all(parent)?; }
        let lock_path = PathBuf::from(format!("{}.lock", self.path.display()));
        let lock = OpenOptions::new().create(true).write(true).open(&lock_path)?;
        flock(&lock, FlockOperation::LockExclusive)?;
        let current = read_state(&self.path);
        let updated = transform(current);
        let payload = serde_json::to_string_pretty(&updated)
            .map(|value| format!("{value}\n"))
            .map_err(|error| std::io::Error::new(std::io::ErrorKind::InvalidData, error))?;
        let result = crate::atomic_io::atomic_write_text(&self.path, &payload, Some(0o600));
        let _ = flock(&lock, FlockOperation::Unlock);
        result.map(|()| updated)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn transaction_serializes_a_single_writer_update() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("boot-health.json");
        let coordinator = UpdateCoordinator::new(&path);
        let updated = coordinator.transaction(|mut state| {
            state.status = "staged".into();
            state.pending_digest = "sha256:new".into();
            state
        }).unwrap();
        assert_eq!(updated.status, "staged");
        assert_eq!(coordinator.read().pending_digest, "sha256:new");
        assert!(path.with_file_name("boot-health.json.lock").is_file());
    }
}
