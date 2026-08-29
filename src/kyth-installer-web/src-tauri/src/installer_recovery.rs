//! Pure transaction-status classification for Rescue mode.
//!
//! This mirrors Python's `recovery.rescue_guidance`: it classifies the last
//! durable status only. Reading state, writing reports, rollback, and reboot
//! remain privileged Python operations.

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub(crate) struct RecoveryGuidance {
    pub status: String,
    pub severity: String,
    pub message: String,
    pub bootable: bool,
}

const GUIDANCE: &[(&str, &str, &str, bool)] = &[
    ("", "unknown", "No install transaction recorded. Do not assume the disk is bootable.", false),
    ("started", "incomplete", "Install started but storage did not finish. Stay in this live session.", false),
    ("prepared", "incomplete", "Install prepared a plan but storage did not finish. Stay in this live session.", false),
    ("storage_complete", "unbootable", "The image is on disk but the installed system is not configured yet. Continue or rescue from this live session — do not reboot into the target.", false),
    ("image_installed", "unbootable", "Legacy journal: image written, configure unknown. Treat the target as not bootable until configure_complete.", false),
    ("configure_started", "unbootable", "Configuring the installed system was interrupted. Continue from this live session — the target is not bootable yet.", false),
    ("configure_complete", "almost", "The installed system is configured. Secure Boot enrollment may still be pending — check MOK staging before reboot.", false),
    ("secure_boot_staged", "ready", "Secure Boot enrollment is staged. Reboot and enroll the MOK if the firmware prompts.", true),
    ("complete", "ready", "Install finished. The target should be bootable.", true),
    ("failed", "failed", "Install failed. Use the log tail and transaction details below.", false),
];

pub(crate) fn rescue_guidance(status: Option<&str>) -> RecoveryGuidance {
    let status = status.unwrap_or_default();
    if let Some((_, severity, message, bootable)) = GUIDANCE.iter().find(|entry| entry.0 == status) {
        return RecoveryGuidance {
            status: status.to_string(),
            severity: (*severity).to_string(),
            message: (*message).to_string(),
            bootable: *bootable,
        };
    }
    RecoveryGuidance {
        status: status.to_string(),
        severity: "unknown".to_string(),
        message: format!("Unrecognized transaction status {status:?}. Do not assume the disk is bootable."),
        bootable: false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    #[test]
    fn shared_recovery_fixture_matches_all_durable_statuses() {
        let cases: Vec<Value> = serde_json::from_str(include_str!("../testdata/recovery_cases.json"))
            .expect("recovery parity fixture must be valid JSON");
        for case in cases {
            let status = case["status"].as_str().expect("status is a string");
            let guidance = rescue_guidance(Some(status));
            assert_eq!(guidance.severity, case["severity"].as_str().unwrap(), "{status}");
            assert_eq!(guidance.bootable, case["bootable"].as_bool().unwrap(), "{status}");
            assert_eq!(guidance.message, case["message"].as_str().unwrap(), "{status}");
        }
        let unknown = rescue_guidance(Some("future_status"));
        assert!(!unknown.bootable);
        assert_eq!(unknown.severity, "unknown");
    }
}
