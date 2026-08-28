//! Port of `kyth_shared.system.hardware_view` — canonical hardware view (first slice).
//! Full `Evaluation`/`Inventory` requires `hardware_policy` port (toml matching,
//! sysfs parsing) — this slice ports the ProbeService-cached shape the Hub
//! actually renders: `has_nvidia`/`is_hybrid`/`capabilities` + applied state,
//! all from the `hardware-summary` probe cache (30s TTL). The live
//! `evaluate_system()` path stays Python until `hardware_policy` is ported.

use std::collections::HashMap;

use serde_json::Value;

#[derive(Debug, Clone, serde::Serialize)]
pub struct HardwareViewSummary {
    pub has_nvidia: bool,
    pub is_hybrid: bool,
    pub capabilities: Vec<String>,
    pub applied: HashMap<String, Value>,
}

pub fn get_hardware_view_summary() -> Option<HardwareViewSummary> {
    // Read via existing probe helper — reuses DISK_TTL 30s and cache_read_paths()
    let raw = crate::system::probe::read_section("hardware-summary")?;
    let obj = raw.as_object()?;
    let has_nvidia = obj.get("has_nvidia").and_then(|v| v.as_bool()).unwrap_or(false);
    let is_hybrid = obj.get("is_hybrid").and_then(|v| v.as_bool()).unwrap_or(false);
    let capabilities = obj
        .get("capabilities")
        .and_then(|v| v.as_array())
        .map(|arr| arr.iter().filter_map(|e| e.as_str().map(|s| s.to_string())).collect())
        .unwrap_or_default();
    // applied state is not in hardware-summary; start empty (Python's read_applied_state() fallback)
    let applied = HashMap::new();
    Some(HardwareViewSummary { has_nvidia, is_hybrid, capabilities, applied })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn returns_option() {
        let _ = get_hardware_view_summary();
    }
}
