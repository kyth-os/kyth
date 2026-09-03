//! Rust-owned install orchestration decisions.
//!
//! The compatibility service still performs phase-specific filesystem work,
//! but it must not be the authority for lifecycle, phase, cancellation, or
//! power decisions. This module is intentionally a small, typed state machine
//! so both the native helper and the compatibility adapter share one
//! fail-closed contract.

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;

const DESTRUCTIVE_CANCEL_MESSAGE: &str =
    "Installation cancelled by user. Disk changes may have already started.";
const SAFE_CANCEL_MESSAGE: &str =
    "Installation cancelled by user before disk changes were committed.";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Lifecycle {
    Idle,
    Validated,
    Partitioning,
    Installing,
    Done,
    Failed,
}

impl Lifecycle {
    fn parse(value: &str) -> Result<Self, String> {
        match value {
            "idle" => Ok(Self::Idle),
            "validated" => Ok(Self::Validated),
            "partitioning" => Ok(Self::Partitioning),
            "installing" => Ok(Self::Installing),
            "done" => Ok(Self::Done),
            "failed" => Ok(Self::Failed),
            other => Err(format!("unknown installer lifecycle: {other}")),
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Idle => "idle",
            Self::Validated => "validated",
            Self::Partitioning => "partitioning",
            Self::Installing => "installing",
            Self::Done => "done",
            Self::Failed => "failed",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
enum Phase {
    Prepare,
    Storage,
    Image,
    Configure,
    SecureBoot,
    Complete,
}

impl Phase {
    fn parse(value: &str) -> Result<Self, String> {
        match value {
            "prepare" => Ok(Self::Prepare),
            "storage" => Ok(Self::Storage),
            "image" => Ok(Self::Image),
            "configure" => Ok(Self::Configure),
            "secure_boot" => Ok(Self::SecureBoot),
            "complete" => Ok(Self::Complete),
            other => Err(format!("unknown installer phase: {other}")),
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Prepare => "prepare",
            Self::Storage => "storage",
            Self::Image => "image",
            Self::Configure => "configure",
            Self::SecureBoot => "secure_boot",
            Self::Complete => "complete",
        }
    }

    fn is_destructive(self) -> bool {
        matches!(
            self,
            Self::Storage | Self::Image | Self::Configure | Self::SecureBoot
        )
    }
}

#[derive(Clone, Debug, Deserialize)]
pub(crate) struct OrchestrationInput {
    pub action: String,
    #[serde(default = "default_idle")]
    pub lifecycle: String,
    #[serde(default = "default_prepare")]
    pub phase: String,
    #[serde(default)]
    pub target: String,
    #[serde(default)]
    pub cancel_requested: bool,
    #[serde(default)]
    pub slot_held: bool,
    #[serde(default)]
    pub status: String,
    #[serde(default)]
    pub next_status: String,
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct OrchestrationResponse {
    pub action: String,
    pub lifecycle: String,
    pub phase: String,
    pub accepted: bool,
    pub cancelled: bool,
    pub cancel_message: String,
    pub status: String,
}

fn default_idle() -> String {
    "idle".to_string()
}
fn default_prepare() -> String {
    "prepare".to_string()
}

fn response(
    input: &OrchestrationInput,
    lifecycle: Lifecycle,
    phase: Phase,
) -> OrchestrationResponse {
    OrchestrationResponse {
        action: input.action.clone(),
        lifecycle: lifecycle.as_str().to_string(),
        phase: phase.as_str().to_string(),
        accepted: true,
        cancelled: false,
        cancel_message: String::new(),
        status: input.next_status.clone(),
    }
}

fn lifecycle_transition(current: Lifecycle, next: Lifecycle) -> bool {
    matches!(
        (current, next),
        (
            Lifecycle::Idle,
            Lifecycle::Validated | Lifecycle::Partitioning | Lifecycle::Failed
        ) | (
            Lifecycle::Validated,
            Lifecycle::Installing | Lifecycle::Failed
        ) | (Lifecycle::Partitioning, Lifecycle::Idle | Lifecycle::Failed)
            | (Lifecycle::Installing, Lifecycle::Done | Lifecycle::Failed)
    )
}

fn status_transition(current: &str, next: &str) -> bool {
    if current == next {
        return true;
    }
    if next == "failed" {
        return true;
    }
    match current {
        "" => matches!(next, "started" | "partitioning"),
        "partitioning" => next == "started",
        "started" => next == "prepared",
        "prepared" => next == "storage_complete",
        "storage_complete" => next == "configure_started",
        "configure_started" => next == "configure_complete",
        "configure_complete" => next == "secure_boot_staged",
        "secure_boot_staged" => next == "complete",
        _ => false,
    }
}

pub(crate) fn apply(input: OrchestrationInput) -> Result<OrchestrationResponse, String> {
    let lifecycle = Lifecycle::parse(&input.lifecycle)?;
    let phase = Phase::parse(&input.phase)?;
    match input.action.as_str() {
        "transition" => {
            let next = Lifecycle::parse(&input.target)?;
            if next != lifecycle && !lifecycle_transition(lifecycle, next) {
                return Err(format!(
                    "Invalid installer lifecycle transition: {} -> {}",
                    lifecycle.as_str(),
                    next.as_str()
                ));
            }
            Ok(response(&input, next, phase))
        }
        "phase" => {
            let next = Phase::parse(&input.target)?;
            if !matches!(
                lifecycle,
                Lifecycle::Idle | Lifecycle::Installing | Lifecycle::Failed
            ) {
                return Err(format!(
                    "Cannot enter installer phase {} while lifecycle is {}",
                    next.as_str(),
                    lifecycle.as_str()
                ));
            }
            if next < phase {
                return Err(format!(
                    "Installer phase cannot move backwards: {} -> {}",
                    phase.as_str(),
                    next.as_str()
                ));
            }
            Ok(response(&input, lifecycle, next))
        }
        "cancel-request" => {
            let mut result = response(&input, lifecycle, phase);
            if !input.slot_held
                || !matches!(lifecycle, Lifecycle::Validated | Lifecycle::Installing)
            {
                result.accepted = false;
            }
            Ok(result)
        }
        "cancel-check" => {
            let mut result = response(&input, lifecycle, phase);
            if input.cancel_requested {
                result.cancelled = true;
                result.cancel_message = if phase.is_destructive() {
                    DESTRUCTIVE_CANCEL_MESSAGE.to_string()
                } else {
                    SAFE_CANCEL_MESSAGE.to_string()
                };
            }
            Ok(result)
        }
        "transaction" => {
            if !status_transition(&input.status, &input.next_status) {
                return Err(format!(
                    "Invalid installer transaction transition: {} -> {}",
                    input.status, input.next_status
                ));
            }
            Ok(response(&input, lifecycle, phase))
        }
        other => Err(format!("unknown installer orchestration action: {other}")),
    }
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct PowerCheck {
    pub status: String,
    pub detail: String,
}

fn power_check_at(root: &Path) -> PowerCheck {
    if !root.is_dir() {
        return PowerCheck {
            status: "pass".to_string(),
            detail: "No battery power constraint detected".to_string(),
        };
    }
    let mut batteries = Vec::new();
    let entries = match fs::read_dir(root) {
        Ok(entries) => entries,
        Err(_) => {
            return PowerCheck {
                status: "pass".to_string(),
                detail: "No battery power constraint detected".to_string(),
            }
        }
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let kind = fs::read_to_string(path.join("type")).ok();
        if kind.as_deref().map(str::trim) != Some("Battery") {
            continue;
        }
        let capacity = fs::read_to_string(path.join("capacity"))
            .ok()
            .and_then(|value| value.trim().parse::<u8>().ok());
        let status = fs::read_to_string(path.join("status"))
            .ok()
            .map(|value| value.trim().to_ascii_lowercase());
        if let (Some(capacity), Some(status)) = (capacity, status) {
            batteries.push((capacity, status));
        }
    }
    let Some((capacity, status)) = batteries.into_iter().min_by_key(|battery| battery.0) else {
        return PowerCheck {
            status: "pass".to_string(),
            detail: "No battery power constraint detected".to_string(),
        };
    };
    if capacity < 20 && matches!(status.as_str(), "discharging" | "not charging") {
        return PowerCheck {
            status: "fail".to_string(),
            detail: format!(
                "Battery is at {capacity}% and is not charging. Connect power before installing."
            ),
        };
    }
    PowerCheck {
        status: "pass".to_string(),
        detail: format!("Battery is {capacity}% ({status})"),
    }
}

pub(crate) fn power_check() -> PowerCheck {
    power_check_at(Path::new("/sys/class/power_supply"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn input(action: &str) -> OrchestrationInput {
        OrchestrationInput {
            action: action.to_string(),
            lifecycle: "idle".to_string(),
            phase: "prepare".to_string(),
            target: String::new(),
            cancel_requested: false,
            slot_held: false,
            status: String::new(),
            next_status: String::new(),
        }
    }

    #[test]
    fn lifecycle_transitions_match_api_contract() {
        let mut request = input("transition");
        request.target = "validated".to_string();
        assert!(apply(request.clone()).is_ok());
        request.target = "done".to_string();
        assert!(apply(request).is_err());
    }

    #[test]
    fn phases_are_monotonic_and_require_active_install() {
        let mut request = input("phase");
        request.target = "storage".to_string();
        assert!(apply(request.clone()).is_ok());
        request.lifecycle = "validated".to_string();
        assert!(apply(request.clone()).is_err());
        request.lifecycle = "installing".to_string();
        request.phase = "configure".to_string();
        request.target = "image".to_string();
        assert!(apply(request).is_err());
    }

    #[test]
    fn cancellation_message_changes_after_destructive_phase() {
        let mut request = input("cancel-check");
        request.cancel_requested = true;
        let safe = apply(request.clone()).unwrap();
        assert_eq!(safe.cancel_message, SAFE_CANCEL_MESSAGE);
        request.phase = "image".to_string();
        let destructive = apply(request).unwrap();
        assert_eq!(destructive.cancel_message, DESTRUCTIVE_CANCEL_MESSAGE);
    }

    #[test]
    fn cancellation_request_rejection_is_a_normal_state_conflict() {
        let request = input("cancel-request");
        let response = apply(request).unwrap();
        assert!(!response.accepted);
    }

    #[test]
    fn transaction_statuses_cannot_skip_recovery_boundaries() {
        let mut request = input("transaction");
        request.next_status = "started".to_string();
        assert!(apply(request.clone()).is_ok());
        request.status = "started".to_string();
        request.next_status = "configure_complete".to_string();
        assert!(apply(request).is_err());
    }

    #[test]
    fn power_probe_matches_compatibility_behavior() {
        let directory = tempfile::tempdir().unwrap();
        let battery = directory.path().join("BAT0");
        fs::create_dir(&battery).unwrap();
        fs::write(battery.join("type"), "Battery\n").unwrap();
        fs::write(battery.join("capacity"), "9\n").unwrap();
        fs::write(battery.join("status"), "Discharging\n").unwrap();
        let result = power_check_at(directory.path());
        assert_eq!(result.status, "fail");
        assert!(result.detail.contains("9%"));
    }
}
