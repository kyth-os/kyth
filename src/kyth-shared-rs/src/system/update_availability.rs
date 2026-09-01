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

/// Project the availability state into the stable Updates-page view model.
/// Collection remains separate so native callers can render a terminal state
/// without taking ownership of network or package-manager orchestration.
pub fn availability_view(
    status: &AvailabilityStatus,
    check_ts: &str,
    staged_ts: Option<&str>,
) -> crate::system::bootc_policy::UpdateAvailabilityView {
    crate::system::bootc_policy::update_availability_view(
        status.staged,
        &status.state,
        status.flatpak_count.max(0) as u32,
        check_ts,
        &status.detail,
        staged_ts,
    )
}

pub fn collect_availability(branch: Option<&str>, use_cached: bool) -> AvailabilityStatus {
    // staged takes precedence — no registry call needed
    let staged = crate::system::bootc::has_staged_update();
    if staged {
        let (flatpak_count, flatpak_detail) = flatpak_updates_count(use_cached);
        return AvailabilityStatus { state: "staged".to_string(), detail: "A staged image is ready to boot.".to_string(), flatpak_count, flatpak_detail, staged: true, manifest_raw: String::new(), blocked_reason: String::new() };
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
    let (flatpak_count, flatpak_detail) = flatpak_updates_count(use_cached);
    AvailabilityStatus { state: registry.state, detail: registry.detail, flatpak_count, flatpak_detail, staged: false, manifest_raw: String::from_utf8_lossy(&registry.manifest_raw).to_string(), blocked_reason: String::new() }
}

/// Return the pending Flatpak count. An explicit Updates-page check bypasses
/// the shared probe cache so a fresh registry result is not paired with stale
/// package-manager data.
pub fn flatpak_updates_count(use_cached: bool) -> (i32, String) {
    if use_cached {
        return (
            crate::system::probe::read_section("flatpak-updates")
                .and_then(|value| value.as_i64())
                .unwrap_or(0)
                .max(0) as i32,
            String::new(),
        );
    }
    let mut total = 0;
    let mut successful_scope = false;
    let mut errors = Vec::new();
    for scope in ["--system", "--user"] {
        let argv = vec![
            "flatpak".to_string(),
            "remote-ls".to_string(),
            "--updates".to_string(),
            scope.to_string(),
            "--columns=application".to_string(),
        ];
        match super::process::run_bounded(&argv, Duration::from_secs(15)) {
            Ok(output) if output.status.success() => {
                successful_scope = true;
                total += String::from_utf8_lossy(&output.stdout)
                    .lines()
                    .filter(|line| !line.trim().is_empty())
                    .count() as i32;
            }
            Ok(output) => {
                let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
                if !detail.is_empty() { errors.push(detail); }
            }
            Err(error) => errors.push(error.to_string()),
        }
    }
    if successful_scope { (total.max(0), String::new()) }
    else { (0, errors.into_iter().next().unwrap_or_else(|| "Flatpak update check unavailable.".to_string())) }
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

    #[test]
    fn projects_terminal_update_state_for_the_native_view() {
        let status = AvailabilityStatus {
            state: "available".into(),
            detail: "2026-08-29".into(),
            flatpak_count: 2,
            flatpak_detail: String::new(),
            staged: false,
            manifest_raw: String::new(),
            blocked_reason: String::new(),
        };
        let view = availability_view(&status, "now", None);
        assert_eq!(view.title, "Update available");
        assert!(view.update_btn_visible);
        assert!(!view.restart_btn_visible);
        assert!(view.body.contains("2 Flatpak updates"));
    }
}
