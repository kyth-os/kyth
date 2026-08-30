//! Deterministic offline repair-plan generation.
//!
//! This is the pure portion of the local AI assistant. It turns probe data
//! into explicit, reviewable actions. It never runs the commands it returns
//! and never contacts a model or network service.

use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AiAction {
    pub id: String,
    pub label: String,
    pub command: Vec<String>,
    pub reason: String,
    pub priority: i64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AiPlan {
    pub actions: Vec<AiAction>,
    pub summary: String,
    pub offline: bool,
    pub model: Option<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct BootStateView {
    pub failures: i64,
    pub status: String,
    pub quarantined: Vec<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct EvaluationView {
    pub capabilities: Vec<String>,
    pub quirks: Vec<Value>,
    pub warnings: Vec<String>,
}

fn action(id: &str, label: impl Into<String>, command: &[&str], reason: impl Into<String>, priority: i64) -> AiAction {
    AiAction { id: id.into(), label: label.into(), command: command.iter().map(|value| (*value).into()).collect(), reason: reason.into(), priority }
}

fn nested<'a>(snapshot: &'a Value, keys: &[&str]) -> Option<&'a Value> {
    keys.iter().try_fold(snapshot, |value, key| value.get(*key))
}

fn should_offer_rollback(snapshot: &Value, state: &BootStateView) -> bool {
    let staged = nested(snapshot, &["bootc-status-data", "status", "staged"]).is_some_and(|value| !value.is_null())
        || nested(snapshot, &["bootc-status", "status", "staged"]).is_some_and(|value| !value.is_null());
    let rollback = nested(snapshot, &["bootc-status-data", "status", "rollback"]).is_some_and(|value| !value.is_null())
        || nested(snapshot, &["bootc-status", "status", "rollback"]).is_some_and(|value| !value.is_null());
    (staged && rollback && state.failures >= 2) || (matches!(state.status.as_str(), "quarantined" | "unhealthy") && rollback)
}

pub fn generate_plan(snapshot: &Value, boot_state: Option<&BootStateView>, evaluation: Option<&EvaluationView>) -> AiPlan {
    let state = boot_state.cloned().unwrap_or_default();
    let mut actions = Vec::new();
    if should_offer_rollback(snapshot, &state) {
        actions.push(action("rollback", "Roll back to previous OS", &["pkexec", "bootc", "rollback"], format!("Staged image has {} failed boots (status={}); rollback is one reboot away.", state.failures, if state.status.is_empty() { "unknown" } else { &state.status }), 10));
        if let Some(digest) = state.quarantined.first() {
            actions.push(AiAction { id: "clear-quarantine".into(), label: "Clear quarantine for staged image".into(), command: vec!["pkexec".into(), "kyth-boot-health".into(), "clear-quarantine".into(), "--digest".into(), digest.clone()], reason: "Quarantined digest is blocking retry; clear to re-stage.".into(), priority: 11 });
        }
    }
    if let Some(updates) = snapshot.get("flatpak-updates").and_then(Value::as_i64).filter(|value| *value > 0) {
        actions.push(action("update-flatpaks", format!("Update {updates} Flatpak(s)"), &["flatpak", "update", "-y"], format!("{updates} Flatpak update(s) pending."), 30));
    }
    if snapshot.get("nvidia-detect") == Some(&Value::Bool(true)) {
        actions.push(action("nvidia-status", "Check NVIDIA driver status", &["/usr/bin/kyth-nvidia-status"], "NVIDIA GPU detected; verify driver build.", 50));
    }
    if snapshot.get("controllers-detect").is_some_and(|value| match value { Value::Object(object) => !object.is_empty() || object.get("devices").is_some_and(|devices| !devices.is_null() && devices != &Value::Array(Vec::new())), Value::Array(items) => !items.is_empty(), Value::Null => false, _ => true }) {
        actions.push(action("controller-check", "Verify controllers", &["/usr/bin/kyth-controller-check"], "Controller hardware detected; verify readiness.", 60));
    }
    if let Some(evaluation) = evaluation {
        if evaluation.capabilities.iter().any(|capability| matches!(capability.as_str(), "gaming.lowlatency" | "gpu.nvidia" | "gpu.amd")) {
            actions.push(action("enable-low-latency", "Enable low-latency gaming", &["ujust", "gaming-low-latency", "on"], "System supports low-latency Vulkan layer (gaming.lowlatency / GPU detected).", 40));
        }
        if let Some(quirk) = evaluation.quirks.iter().find(|quirk| quirk.get("expires_on").is_some_and(|value| !value.as_str().unwrap_or_default().is_empty())) {
            let id = quirk.get("id").and_then(Value::as_str).unwrap_or("unknown");
            let expires = quirk.get("expires_on").and_then(Value::as_str).unwrap_or_default();
            let reason = quirk.get("reason").and_then(Value::as_str).unwrap_or_default();
            actions.push(action(&format!("review-quirk-{id}"), format!("Review quirk {id}"), &["kyth-hardware-policy", "validate", "--fail-expired"], format!("Quirk {id} expires {expires}: {reason}"), 70));
        }
        if !evaluation.warnings.is_empty() {
            actions.push(action("hardware-policy-warnings", "Review hardware policy warnings", &["kyth-hardware-policy", "status"], evaluation.warnings.iter().take(2).cloned().collect::<Vec<_>>().join("; "), 80));
        }
    }
    if snapshot.is_null() || snapshot.as_object().is_some_and(|object| object.is_empty()) {
        actions.push(action("refresh-probe", "Refresh system probe cache", &["/usr/libexec/kyth-probe"], "Probe snapshot empty; refresh cache to diagnose.", 90));
    }
    actions.sort_by_key(|item| item.priority);
    let summary = if actions.is_empty() { "System looks healthy. No repair actions needed.".into() } else {
        let mut summary = format!("{} action(s): {}", actions.len(), actions.iter().take(3).map(|item| item.label.as_str()).collect::<Vec<_>>().join(", "));
        if actions.len() > 3 { summary.push_str(&format!(" +{} more", actions.len() - 3)); }
        summary
    };
    AiPlan { actions, summary, offline: true, model: None }
}

pub fn plan_from_json(value: &Value) -> Option<AiPlan> {
    serde_json::from_value(value.clone()).ok().map(|mut plan: AiPlan| {
        plan.actions.sort_by_key(|action| action.priority);
        plan
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generates_ordered_rollback_and_health_actions() {
        let snapshot = serde_json::json!({"bootc-status-data":{"status":{"staged":"new","rollback":"old"}}, "flatpak-updates": 2, "nvidia-detect": true});
        let state = BootStateView { failures: 2, status: "unhealthy".into(), quarantined: vec!["sha256:bad".into()] };
        let evaluation = EvaluationView { capabilities: vec!["gpu.amd".into()], warnings: vec!["expired quirk".into()], ..Default::default() };
        let plan = generate_plan(&snapshot, Some(&state), Some(&evaluation));
        assert_eq!(plan.actions[0].id, "rollback");
        assert!(plan.actions.iter().any(|action| action.id == "clear-quarantine"));
        assert!(plan.actions.iter().any(|action| action.id == "update-flatpaks"));
        assert!(plan.actions.iter().any(|action| action.id == "enable-low-latency"));
    }

    #[test]
    fn empty_snapshot_is_a_safe_refresh_suggestion() {
        let plan = generate_plan(&serde_json::json!({}), None, None);
        assert_eq!(plan.actions.len(), 1);
        assert_eq!(plan.actions[0].id, "refresh-probe");
        assert!(plan.summary.contains("Refresh system probe"));
    }

    #[test]
    fn parses_and_orders_serialized_plans() {
        let value = serde_json::json!({"actions":[{"id":"late","label":"Late","command":[],"reason":"","priority":90},{"id":"early","label":"Early","command":[],"reason":"","priority":10}],"summary":"x","offline":true,"model":null});
        let plan = plan_from_json(&value).unwrap();
        assert_eq!(plan.actions[0].id, "early");
    }
}
