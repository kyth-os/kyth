//! Port of `kyth_shared.system.update_status` — watcher snapshot and
//! TTL-bounded check_state.

use serde::Deserialize;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

pub const DEFAULT_UPDATE_STATUS_PATH: &str = "/var/lib/kyth/update-watcher-status.json";

/// Read-only projection of the cross-process watcher state. The watcher and
/// its atomic writer remain Python-owned; Rust only consumes this file.
#[derive(Debug, Clone, Default, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct UpdateSnapshot {
    pub result: String,
    pub reason: Option<String>,
    pub output: String,
    pub ts: i64,
    pub flatpak_updates: i64,
    pub image_ref: String,
    pub booted_digest: String,
    pub staged_digest: String,
    pub remote_digest: String,
    pub retryable: bool,
}

impl UpdateSnapshot {
    /// Match Python's `UpdateSnapshot.system_state` projection used by the
    /// welcome screen and notification policy.
    pub fn system_state(&self) -> &'static str {
        if self.result == "quarantined" && self.staged_digest.is_empty() {
            return "uptodate";
        }
        if matches!(self.result.as_str(), "skipped" | "error") && self.staged_digest.is_empty() {
            return "unknown";
        }
        if !self.staged_digest.is_empty()
            || self.result == "upgraded"
            || self.reason.as_deref().is_some_and(|reason| reason.to_lowercase().contains("already staged"))
        {
            return "staged";
        }
        if !self.booted_digest.is_empty() && !self.remote_digest.is_empty() {
            return if self.booted_digest == self.remote_digest { "uptodate" } else { "available" };
        }
        if self.result == "no_change" && self.output.to_lowercase().contains("already up to date") {
            return "uptodate";
        }
        "unknown"
    }
}

/// Read and age-check a watcher snapshot without spawning a command.
/// `now` is injectable so tests never depend on mutable global clock state.
pub fn read_update_snapshot_in(path: impl AsRef<Path>, max_age: i64, now: i64) -> Option<UpdateSnapshot> {
    let text = std::fs::read_to_string(path).ok()?;
    let snapshot = serde_json::from_str::<UpdateSnapshot>(&text).ok()?;
    if snapshot.ts <= 0 || now.saturating_sub(snapshot.ts) > max_age {
        return None;
    }
    Some(snapshot)
}

pub fn read_update_snapshot(max_age: i64) -> Option<UpdateSnapshot> {
    let now = SystemTime::now().duration_since(UNIX_EPOCH).ok()?.as_secs() as i64;
    read_update_snapshot_in(DEFAULT_UPDATE_STATUS_PATH, max_age, now)
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateStatus {
    pub booted: Option<String>,
    pub staged: bool,
    pub rollback: bool,
    pub remote_digest: Option<String>,
    pub blocked_reason: Option<String>,
    pub retry_cmd: Option<String>,
    pub check_state: String,
    pub detail: String,
}

pub fn check_update_status() -> UpdateStatus {
    let data = crate::system::probe::read_section("bootc-status-data")
        .or_else(|| crate::system::bootc_query::fetch_status_data());
    let watcher = read_update_snapshot(600);
    let watcher_staged = watcher.as_ref().is_some_and(|snapshot| !snapshot.staged_digest.is_empty());
    let staged = data.as_ref().is_some_and(|value| crate::system::bootc::deployment_present(value, "staged")) || watcher_staged;
    let rollback = data.as_ref().is_some_and(|value| crate::system::bootc::deployment_present(value, "rollback"));
    let booted = data.as_ref().and_then(crate::system::registry::booted_image_digest);
    let branch = crate::system::bootc::current_branch().unwrap_or_else(|| "latest".to_string());
    let Some(data) = data else {
        return UpdateStatus { booted: None, staged, rollback, remote_digest: None, blocked_reason: Some("Could not read bootc status.".to_string()), retry_cmd: Some("bootc upgrade --check".to_string()), check_state: "error".to_string(), detail: "Could not read bootc status.".to_string() };
    };
    let registry = crate::system::registry::check_registry_update(&data, &branch, crate::system::bootc_policy::REGISTRY);
    if registry.state == "error" {
        return UpdateStatus { booted, staged, rollback, remote_digest: None, blocked_reason: Some(registry.detail.clone()), retry_cmd: Some("bootc upgrade --check".to_string()), check_state: "error".to_string(), detail: registry.detail };
    }
    let remote_digest = crate::system::registry::remote_digest_and_timestamp(&registry.manifest_raw).0;
    let mut check_state = "uptodate".to_string();
    let mut detail = registry.detail;
    if let Some(rd) = &remote_digest {
        if Some(rd) != booted.as_ref() {
            check_state = "available".to_string();
        }
    }
    if staged {
        check_state = "available".to_string();
        if detail.is_empty() { detail = watcher.as_ref().and_then(|snapshot| snapshot.reason.clone()).unwrap_or_else(|| "staged image pending".to_string()); }
    }
    UpdateStatus { booted, staged, rollback, remote_digest, blocked_reason: None, retry_cmd: None, check_state, detail }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn reads_fresh_watcher_snapshot() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("update-status.json");
        fs::write(&path, r#"{"result":"staged","ts":100,"staged_digest":"sha256:test"}"#).unwrap();
        let snapshot = read_update_snapshot_in(path, 600, 150).unwrap();
        assert_eq!(snapshot.result, "staged");
        assert_eq!(snapshot.staged_digest, "sha256:test");
        assert_eq!(snapshot.system_state(), "staged");
    }

    #[test]
    fn ignores_missing_or_stale_watcher_snapshot() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("update-status.json");
        fs::write(&path, r#"{"result":"staged","ts":100}"#).unwrap();
        assert!(read_update_snapshot_in(&path, 600, 701).is_none());
        assert!(read_update_snapshot_in(dir.path().join("missing.json"), 600, 100).is_none());
    }

    #[test]
    fn watcher_projection_respects_quarantine_and_digest_states() {
        let mut snapshot = UpdateSnapshot { result: "quarantined".into(), ..Default::default() };
        assert_eq!(snapshot.system_state(), "uptodate");
        snapshot.result = "checked".into();
        snapshot.booted_digest = "sha256:a".into();
        snapshot.remote_digest = "sha256:b".into();
        assert_eq!(snapshot.system_state(), "available");
        snapshot.staged_digest = "sha256:c".into();
        assert_eq!(snapshot.system_state(), "staged");
    }

    #[test]
    fn returns_status() {
        let s = check_update_status();
        assert!(["available","uptodate","error","idle","checking"].contains(&s.check_state.as_str()));
    }
}
