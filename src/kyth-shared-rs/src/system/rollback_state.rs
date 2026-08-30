//! Single-source staged/rollback state used by update UI.

use serde::Deserialize;
use std::path::Path;

pub const DEFAULT_STATE_PATH: &str = "/var/lib/kyth/hub_state.json";

#[derive(Debug, Clone, Default, PartialEq, Eq, Deserialize)]
#[serde(default)]
pub struct UpdateCoordinatorState {
    pub staged: bool,
    pub rollback_available: bool,
}

pub fn read_state(path: impl AsRef<Path>) -> UpdateCoordinatorState {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or_default()
}

pub fn read_default_state() -> UpdateCoordinatorState {
    read_state(DEFAULT_STATE_PATH)
}

pub fn is_rollback_available(state: &UpdateCoordinatorState) -> bool {
    state.staged && state.rollback_available
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn reads_fail_safe_coordinator_state() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("hub-state.json");
        fs::write(&path, r#"{"staged":true,"rollback_available":true}"#).unwrap();
        let state = read_state(&path);
        assert!(is_rollback_available(&state));
        fs::write(&path, "not json").unwrap();
        assert_eq!(read_state(&path), UpdateCoordinatorState::default());
    }
}
