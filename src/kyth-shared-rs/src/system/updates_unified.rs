//! Port of `kyth_shared.system.updates_unified` — bootc + flatpak + firmware.

pub fn pending_updates_summary() -> std::collections::HashMap<String, String> {
    let firmware = crate::system::firmware::check_firmware_updates(20);
    // flatpak
    let (flatpak_count, flatpak_detail) =
        crate::system::update_availability::flatpak_updates_count(false);
    // bootc
    let bootc = crate::system::bootc_query::fetch_status_data()
        .map(|data| {
            if crate::system::bootc::deployment_present(&data, "staged") {
                "staged"
            } else {
                "current"
            }
            .to_string()
        })
        .unwrap_or_else(|| "unknown".to_string());
    build_summary(firmware, flatpak_count, &flatpak_detail, bootc)
}

/// Pure summary assembly from already-collected values, so the mapping is
/// unit-testable without running live fwupdmgr/flatpak/bootc collectors on
/// the test host. An indeterminate source reports `"unknown"` — never a
/// fabricated `0` (firmware) — mirroring the bootc entry's convention.
fn build_summary(
    firmware: Option<u32>,
    flatpak_count: i32,
    flatpak_detail: &str,
    bootc: String,
) -> std::collections::HashMap<String, String> {
    let mut out = std::collections::HashMap::new();
    out.insert(
        "firmware".to_string(),
        firmware
            .map(|count| count.to_string())
            .unwrap_or_else(|| "unknown".to_string()),
    );
    out.insert("flatpak".to_string(), flatpak_count.to_string());
    if !flatpak_detail.is_empty() {
        out.insert("flatpak_detail".to_string(), flatpak_detail.to_string());
    }
    out.insert("bootc".to_string(), bootc);
    out
}

pub fn rollback_command() -> Vec<String> {
    vec!["bootc".to_string(), "rollback".to_string()]
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn summary_maps_injected_values() {
        let m = build_summary(Some(3), 5, "", "staged".to_string());
        assert_eq!(m["firmware"], "3");
        assert_eq!(m["flatpak"], "5");
        assert_eq!(m["bootc"], "staged");
        assert!(!m.contains_key("flatpak_detail"));
    }
    #[test]
    fn summary_reports_indeterminate_firmware_as_unknown_not_zero() {
        let m = build_summary(None, 0, "", "unknown".to_string());
        assert_eq!(m["firmware"], "unknown");
        assert_eq!(m["bootc"], "unknown");
    }
    #[test]
    fn summary_includes_flatpak_detail_only_when_present() {
        let m = build_summary(Some(0), 2, "user scope failed", "current".to_string());
        assert_eq!(m["firmware"], "0");
        assert_eq!(m["flatpak_detail"], "user scope failed");
    }
    #[test]
    fn rollback() {
        assert_eq!(rollback_command(), vec!["bootc", "rollback"]);
    }
}
