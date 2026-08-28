//! Port of `kyth_shared.system.recovery_status` — staged/rollback/quarantined single view.

use std::collections::HashMap;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RecoveryStatus {
    pub has_staged: bool,
    pub has_rollback: bool,
    pub quarantined_digest: String,
    pub quarantine_detail: String,
    pub watcher_staged: bool,
    pub clear_quarantine_cmd: String,
}

pub fn recovery_banner(s: &RecoveryStatus) -> String {
    let key = (s.has_staged, s.has_rollback, !s.quarantined_digest.is_empty());
    match key {
        (false, false, false) => "up-to-date".to_string(),
        (true, false, false) => "reboot to apply staged".to_string(),
        (true, true, false) => "reboot to apply staged".to_string(),
        (false, true, false) => "rollback available".to_string(),
        (_, _, true) => "quarantined — clear-quarantine retry".to_string(),
    }
}

pub fn get_recovery_status() -> RecoveryStatus {
    // Read via probe/cache + boot health — simplified live version:
    // has_staged/has_rollback via deployment_history, quarantined via file existence
    let history = crate::system::deployment_history::deployment_history();
    let has_staged = history.iter().find(|d| d.section=="staged").map(|d| d.available).unwrap_or(false);
    let has_rollback = history.iter().find(|d| d.section=="rollback").map(|d| d.available).unwrap_or(false);
    // quarantine: /var/lib/kyth/boot-health.json contains quarantined digest?
    let mut quarantined = String::new();
    let mut detail = String::new();
    if let Ok(text) = std::fs::read_to_string("/var/lib/kyth/boot-health.json") {
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(&text) {
            if let Some(q) = v.get("quarantined_digest").and_then(|x| x.as_str()) {
                if !q.is_empty() { quarantined = q.to_string(); detail = "boot quarantine active".to_string(); }
            }
        }
    }
    let clear_cmd = if !quarantined.is_empty() { format!("sudo kyth-boot-health clear-quarantine --digest {}", quarantined) } else { String::new() };
    RecoveryStatus { has_staged, has_rollback, quarantined_digest: quarantined, quarantine_detail: detail, watcher_staged: has_staged, clear_quarantine_cmd: clear_cmd }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn banner_staged() {
        let s = RecoveryStatus { has_staged:true, has_rollback:false, quarantined_digest:String::new(), quarantine_detail:String::new(), watcher_staged:true, clear_quarantine_cmd:String::new() };
        assert_eq!(recovery_banner(&s), "reboot to apply staged");
    }
    #[test]
    fn banner_quarantined() {
        let s = RecoveryStatus { has_staged:false, has_rollback:false, quarantined_digest:"abc".to_string(), quarantine_detail:String::new(), watcher_staged:false, clear_quarantine_cmd:String::new() };
        assert_eq!(recovery_banner(&s), "quarantined — clear-quarantine retry");
    }
}
