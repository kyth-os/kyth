//! Port of `kyth_shared.system.update_availability` — Hub-side 15s deadline.

use std::time::Duration;

#[derive(Debug, Clone)]
pub struct AvailabilityStatus {
    pub state: String,
    pub detail: String,
    pub flatpak_count: i32,
    pub flatpak_detail: String,
    pub staged: bool,
    pub manifest_raw: String,
    pub blocked_reason: String,
}

pub fn collect_availability(branch: Option<&str>, use_cached: bool) -> AvailabilityStatus {
    // staged takes precedence — no registry call needed
    let staged = crate::system::bootc::has_staged_update();
    if staged {
        let flatpak = if use_cached {
            crate::system::probe::read_section("flatpak-updates").and_then(|v| v.as_i64()).map(|n| n as i32).unwrap_or(0)
        } else { 0 };
        return AvailabilityStatus { state: "staged".to_string(), detail: "A staged image is ready to boot.".to_string(), flatpak_count: flatpak.max(0), flatpak_detail: String::new(), staged: true, manifest_raw: String::new(), blocked_reason: String::new() };
    }
    let b = branch.map(str::to_string).or_else(crate::system::bootc::current_branch).unwrap_or_else(|| "latest".to_string());
    let status_data = crate::system::probe::read_section("bootc-status-data")
        .or_else(|| crate::system::bootc_query::fetch_status_data());
    let Some(status_data) = status_data else {
        return AvailabilityStatus { state: "error".to_string(), detail: "Could not read bootc status.".to_string(), flatpak_count: 0, flatpak_detail: String::new(), staged: false, manifest_raw: String::new(), blocked_reason: String::new() };
    };
    let registry = crate::system::registry::check_registry_update(&status_data, &b, crate::system::bootc_policy::REGISTRY);
    if registry.state == "error" {
        return AvailabilityStatus { state: "error".to_string(), detail: registry.detail, flatpak_count: 0, flatpak_detail: String::new(), staged: false, manifest_raw: String::from_utf8_lossy(&registry.manifest_raw).to_string(), blocked_reason: String::new() };
    }
    // Flatpak count with nmcli skip if disconnected
    let nm = run_nmcli_state();
    if matches!(nm.as_deref(), Some("disconnected") | Some("asleep") | Some("unknown")) {
        return AvailabilityStatus { state: registry.state, detail: registry.detail, flatpak_count: 0, flatpak_detail: String::new(), staged: false, manifest_raw: String::from_utf8_lossy(&registry.manifest_raw).to_string(), blocked_reason: String::new() };
    }
    let flatpak_count = crate::system::probe::read_section("flatpak-updates")
        .and_then(|v| v.as_i64())
        .map(|n| n as i32)
        .unwrap_or(0)
        .max(0);
    AvailabilityStatus { state: registry.state, detail: registry.detail, flatpak_count, flatpak_detail: String::new(), staged: false, manifest_raw: String::from_utf8_lossy(&registry.manifest_raw).to_string(), blocked_reason: String::new() }
}

fn run_nmcli_state() -> Option<String> {
    let argv = ["nmcli", "-t", "-f", "STATE", "general"].into_iter().map(String::from).collect::<Vec<_>>();
    let output = super::process::run_bounded(&argv, Duration::from_secs(2)).ok()?;
    output.status.success().then(|| String::from_utf8_lossy(&output.stdout).trim().to_lowercase())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn collect_returns() {
        let s = collect_availability(None, true);
        assert!(["staged","uptodate","available","error"].contains(&s.state.as_str()));
    }
}
