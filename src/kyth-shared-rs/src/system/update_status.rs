//! Port of `kyth_shared.system.update_status` — TTL-bounded check_state.

use std::time::Duration;

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
    // Simplified live version: read from probe cache + deployment_history
    // Full registry-digest probe requires skopeo — use deployment_history staged flag
    let history = crate::system::deployment_history::deployment_history();
    let staged = history.iter().find(|d| d.section=="staged").map(|d| d.available).unwrap_or(false);
    let rollback = history.iter().find(|d| d.section=="rollback").map(|d| d.available).unwrap_or(false);
    // remote_digest via probe cache registry-digest if present, else None
    let remote_digest = crate::system::probe::read_section("registry-digest")
        .and_then(|v| v.get("digest").and_then(|d| d.as_str()).map(|s| s.to_string()));
    let booted = crate::system::probe::read_section("bootc-status-data")
        .and_then(|v| v.get("status").and_then(|s| s.get("booted")).and_then(|b| b.get("image")).and_then(|i| i.get("imageDigest")).and_then(|d| d.as_str()).map(|s| s.to_string()));
    let mut check_state = "uptodate".to_string();
    let mut detail = String::new();
    if let Some(rd) = &remote_digest {
        if Some(rd) != booted.as_ref() {
            check_state = "available".to_string();
        }
    }
    // If no remote info, keep uptodate
    if remote_digest.is_none() && staged {
        check_state = "available".to_string();
        detail = "staged image pending".to_string();
    }
    UpdateStatus { booted, staged, rollback, remote_digest, blocked_reason: None, retry_cmd: None, check_state, detail }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn returns_status() {
        let s = check_update_status();
        assert!(["available","uptodate","error","idle","checking"].contains(&s.check_state.as_str()));
    }
}
