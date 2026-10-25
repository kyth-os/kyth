//! Native Hub availability check with a bounded 90s deadline.

use std::time::{Duration, Instant};

pub const AVAILABILITY_TIMEOUT: Duration = Duration::from_secs(90);

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

fn error_status(detail: impl Into<String>) -> AvailabilityStatus {
    let detail = detail.into();
    AvailabilityStatus {
        state: "error".to_string(),
        blocked_reason: detail.clone(),
        detail,
        flatpak_count: 0,
        flatpak_detail: String::new(),
        staged: false,
        manifest_raw: String::new(),
    }
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

pub fn collect_availability(use_cached: bool) -> AvailabilityStatus {
    let deadline = Instant::now() + AVAILABILITY_TIMEOUT;
    // staged takes precedence — no registry call needed
    let staged = crate::system::bootc::has_staged_update();
    if staged {
        let (flatpak_count, flatpak_detail) = flatpak_updates_count_until(use_cached, deadline);
        return AvailabilityStatus {
            state: "staged".to_string(),
            detail: "A staged image is ready to boot.".to_string(),
            flatpak_count,
            flatpak_detail,
            staged: true,
            manifest_raw: String::new(),
            blocked_reason: String::new(),
        };
    }

    // The check follows the image reference already tracked by the
    // deployment. The old independent skopeo/tag probe could time out or
    // disagree with bootc, and NetworkManager's "unknown" state is not proof
    // that the host cannot reach the registry.
    let remaining = deadline.saturating_duration_since(Instant::now());
    let check_output = match crate::system::bootc_query::update_check(remaining) {
        Ok(output) => output,
        Err(detail) => return error_status(detail),
    };
    let Some(state) = crate::system::bootc_query::update_check_state(&check_output) else {
        return error_status("Could not determine the result of the bootc update check.");
    };
    let (flatpak_count, flatpak_detail) = flatpak_updates_count_until(use_cached, deadline);
    AvailabilityStatus {
        state: state.to_string(),
        detail: check_output,
        flatpak_count,
        flatpak_detail,
        staged: false,
        manifest_raw: String::new(),
        blocked_reason: String::new(),
    }
}

/// argv for one installation's pending **app** updates. `--app` matters:
/// without it `remote-ls --updates` also lists updatable runtimes, and the
/// Hub presented that raw line count as "app updates" that its own
/// `flatpak update` verdict then had to explain away.
fn remote_ls_updates_argv(scope: &str) -> Vec<String> {
    vec![
        "flatpak".to_string(),
        "remote-ls".to_string(),
        "--updates".to_string(),
        "--app".to_string(),
        scope.to_string(),
        "--columns=application".to_string(),
    ]
}

/// Return the pending Flatpak count. An explicit Updates-page check bypasses
/// the shared probe cache so a fresh registry result is not paired with stale
/// package-manager data.
pub fn flatpak_updates_count(use_cached: bool) -> (i32, String) {
    if use_cached {
        return cached_flatpak_count();
    }
    // Per-scope deadlines: each installation gets its own full 30 s budget.
    // The old single shared deadline let a slow system-scope query consume
    // the user scope's time, so the post-update verification recount could
    // fail purely because the first scope was slow.
    count_flatpak_scopes(|| Instant::now() + Duration::from_secs(30))
}

fn flatpak_updates_count_until(use_cached: bool, deadline: Instant) -> (i32, String) {
    if use_cached {
        return cached_flatpak_count();
    }
    count_flatpak_scopes(|| deadline)
}

fn cached_flatpak_count() -> (i32, String) {
    (
        crate::system::probe::read_section("flatpak-updates")
            .and_then(|value| value.as_i64())
            .unwrap_or(0)
            .max(0) as i32,
        String::new(),
    )
}

fn count_flatpak_scopes(deadline_for: impl Fn() -> Instant) -> (i32, String) {
    let mut total = 0;
    let mut successful_scope = false;
    let mut errors = Vec::new();
    for scope in ["--system", "--user"] {
        let argv = remote_ls_updates_argv(scope);
        let timeout = deadline_for().saturating_duration_since(Instant::now());
        match super::process::run_bounded(&argv, timeout) {
            Ok(output) if output.status.success() => {
                successful_scope = true;
                total += parse_pending_ids(&String::from_utf8_lossy(&output.stdout)).len() as i32;
            }
            Ok(output) => {
                let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
                if !detail.is_empty() {
                    errors.push(detail);
                }
            }
            Err(error) => errors.push(error.to_string()),
        }
    }
    flatpak_scope_result(total, successful_scope, &errors)
}

fn flatpak_scope_result(total: i32, successful_scope: bool, errors: &[String]) -> (i32, String) {
    if successful_scope {
        let detail = if errors.is_empty() {
            String::new()
        } else {
            "Flatpak update status could not be checked for every installation.".to_string()
        };
        (total.max(0), detail)
    } else {
        (
            0,
            errors
                .first()
                .map(|detail| crate::system::process::redact_sensitive_text(detail))
                .unwrap_or_else(|| "Flatpak update check unavailable.".to_string()),
        )
    }
}

/// One installation's pending/masked picture, gathered live by
/// `flatpak_update_completion` and consumed by the pure
/// `diagnose_flatpak_completion`. Masks are per-installation: an app masked
/// in the system installation is NOT held back in the user installation, so
/// the two must never be merged before the stuck/pinned split.
#[derive(Debug, Clone, Default)]
pub struct ScopePending {
    pub pending: Vec<String>,
    pub masked: Vec<String>,
}

/// Pure completion verdict for the post-update recount. Separated from the
/// subprocess gathering so the pinned/stuck/verification branches are
/// unit-testable without a live flatpak (the old inline version shelled out
/// mid-function, which made its most important branches untestable).
pub fn diagnose_flatpak_completion(
    remaining: i32,
    verification_detail: &str,
    scopes: &[ScopePending],
) -> Result<String, String> {
    let remaining = remaining.max(0);
    if remaining > 0 {
        // Don't just report a count and tell the user to retry forever.
        // Identify WHICH apps are stuck and WHY: masked/pinned apps are
        // intentionally held back (not a failure), while unmasked apps
        // that survive `flatpak update` need specific attention. An app is
        // stuck only when it is pending in an installation where it is not
        // masked; a mask in the other installation does not hold it back.
        let mut pending_ids: Vec<String> = Vec::new();
        let mut stuck_ids: Vec<String> = Vec::new();
        for scope in scopes {
            for id in &scope.pending {
                if !pending_ids.contains(id) {
                    pending_ids.push(id.clone());
                }
                if !scope.masked.contains(id) && !stuck_ids.contains(id) {
                    stuck_ids.push(id.clone());
                }
            }
        }
        pending_ids.sort();
        stuck_ids.sort();
        if stuck_ids.is_empty() && !pending_ids.is_empty() {
            let names = pending_ids.join(", ");
            return Ok(format!(
                "App updates finished. {remaining} update(s) remain pinned ({names}); unpin them to update."
            ));
        }
        let pending = if remaining == 1 {
            "1 app update remains".to_string()
        } else {
            format!("{remaining} app updates remain")
        };
        let stuck_detail = if stuck_ids.is_empty() {
            String::new()
        } else {
            format!(" Stuck apps: {}.", stuck_ids.join(", "))
        };
        let detail = if verification_detail.is_empty() {
            format!("Flatpak update commands finished, but {pending}.{stuck_detail}")
        } else {
            let safe_detail = crate::system::process::redact_sensitive_text(verification_detail);
            format!("Flatpak update commands finished, but {pending}; verification: {safe_detail}.{stuck_detail}")
        };
        return Err(detail);
    }
    if !verification_detail.is_empty() {
        // Both update phases already succeeded; only the recount was
        // imperfect (a scope could not be re-checked in time). Reporting
        // the whole update as FAILED here trained users to distrust the
        // result and retry blindly — the updates themselves are applied.
        // Report success with the verification caveat; the Apps page
        // re-reads the authoritative count right after anyway.
        let safe_detail = crate::system::process::redact_sensitive_text(verification_detail);
        return Ok(format!(
            "App updates finished. The final check was incomplete ({safe_detail}); check for updates again to confirm none remain."
        ));
    }
    Ok("App updates finished. No app updates remain.".to_string())
}

pub fn flatpak_update_completion(
    remaining: i32,
    verification_detail: &str,
) -> Result<String, String> {
    let scopes = if remaining.max(0) > 0 {
        ["--system", "--user"]
            .iter()
            .map(|scope| ScopePending {
                pending: flatpak_pending_update_ids_for(scope),
                masked: flatpak_masked_ids_for(scope),
            })
            .collect::<Vec<_>>()
    } else {
        Vec::new()
    };
    diagnose_flatpak_completion(remaining, verification_detail, &scopes)
}

/// Parse `remote-ls --updates --columns=application` output: one app id
/// per non-empty line.
pub fn parse_pending_ids(raw: &str) -> Vec<String> {
    raw.lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(str::to_string)
        .collect()
}

/// Returns the sorted, deduplicated list of application IDs with pending
/// updates in one installation (from `flatpak remote-ls --updates --app`).
/// Used to diagnose WHY updates remain after `flatpak update` exits
/// successfully.
pub fn flatpak_pending_update_ids_for(scope: &str) -> Vec<String> {
    let argv = remote_ls_updates_argv(scope);
    let timeout = std::time::Duration::from_secs(30);
    let mut ids = Vec::new();
    if let Ok(output) = super::process::run_bounded(&argv, timeout) {
        if output.status.success() {
            ids = parse_pending_ids(&String::from_utf8_lossy(&output.stdout));
        }
    }
    ids.sort();
    ids.dedup();
    ids
}

/// Returns the sorted, deduplicated list of application IDs with pending
/// updates across both installations.
pub fn flatpak_pending_update_ids() -> Vec<String> {
    let mut ids: Vec<String> = ["--system", "--user"]
        .iter()
        .flat_map(|scope| flatpak_pending_update_ids_for(scope))
        .collect();
    ids.sort();
    ids.dedup();
    ids
}

/// Parse `flatpak mask` output: one "app-id [branch]" per line, `#`
/// comments and blank lines skipped.
pub fn parse_masked_ids(raw: &str) -> Vec<String> {
    raw.lines()
        .map(str::trim)
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .filter_map(|line| line.split_whitespace().next())
        .map(str::to_string)
        .collect()
}

/// Returns the sorted, deduplicated list of masked (pinned) app IDs in one
/// installation. A "remaining" update for a masked app is not a failure —
/// it's the user/admin's explicit choice.
pub fn flatpak_masked_ids_for(scope: &str) -> Vec<String> {
    let argv = vec!["flatpak".to_string(), "mask".to_string(), scope.to_string()];
    let timeout = std::time::Duration::from_secs(10);
    let mut ids = Vec::new();
    if let Ok(output) = super::process::run_bounded(&argv, timeout) {
        if output.status.success() {
            ids = parse_masked_ids(&String::from_utf8_lossy(&output.stdout));
        }
    }
    ids.sort();
    ids.dedup();
    ids
}

/// Returns the sorted, deduplicated list of masked (pinned) app IDs across
/// both installations.
pub fn flatpak_masked_ids() -> Vec<String> {
    let mut ids: Vec<String> = ["--system", "--user"]
        .iter()
        .flat_map(|scope| flatpak_masked_ids_for(scope))
        .collect();
    ids.sort();
    ids.dedup();
    ids
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn collect_returns() {
        let s = collect_availability(true);
        assert!(["staged", "uptodate", "available", "error"].contains(&s.state.as_str()));
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

    #[test]
    fn partial_flatpak_scope_failure_never_looks_like_a_clean_zero() {
        let (count, detail) =
            flatpak_scope_result(0, true, &["system installation query failed".to_string()]);
        assert_eq!(count, 0);
        assert_eq!(
            detail,
            "Flatpak update status could not be checked for every installation."
        );
    }

    #[test]
    fn flatpak_completion_requires_zero_verified_updates() {
        let remaining = flatpak_update_completion(2, "").unwrap_err();
        assert!(remaining.contains("2 app updates remain"));
    }

    #[test]
    fn flatpak_completion_reports_single_remaining_update_correctly() {
        let remaining = flatpak_update_completion(1, "").unwrap_err();
        assert!(remaining.contains("1 app update remains"));
    }

    #[test]
    fn flatpak_completion_with_imperfect_verification_is_success_with_a_caveat() {
        // Both update phases succeeded; only the recount was imperfect.
        // That must not flip the job to FAILED (the old behavior), or a
        // slow remote-ls after a good update reads as a failed update.
        let outcome = flatpak_update_completion(0, "system installation unavailable").unwrap();
        assert!(outcome.contains("App updates finished."));
        assert!(outcome.contains("final check was incomplete"));
    }

    #[test]
    fn flatpak_completion_reports_success_only_after_no_updates_remain() {
        assert_eq!(
            flatpak_update_completion(0, "").unwrap(),
            "App updates finished. No app updates remain."
        );
    }

    #[test]
    fn diagnose_reports_all_remaining_as_pinned_when_every_pending_is_masked() {
        let scopes = vec![ScopePending {
            pending: vec!["org.example.Held".to_string()],
            masked: vec!["org.example.Held".to_string()],
        }];
        let outcome = diagnose_flatpak_completion(1, "", &scopes).unwrap();
        assert!(outcome.contains("remain pinned"));
        assert!(outcome.contains("org.example.Held"));
    }

    #[test]
    fn diagnose_names_unmasked_remaining_apps_as_stuck() {
        let scopes = vec![ScopePending {
            pending: vec![
                "org.example.Held".to_string(),
                "org.example.Stuck".to_string(),
            ],
            masked: vec!["org.example.Held".to_string()],
        }];
        let outcome = diagnose_flatpak_completion(2, "", &scopes).unwrap_err();
        assert!(outcome.contains("2 app updates remain"));
        assert!(outcome.contains("Stuck apps: org.example.Stuck."));
    }

    #[test]
    fn diagnose_mask_in_the_other_installation_does_not_unstick_an_app() {
        // Pending as a user app, masked only in the system installation:
        // the user-scope update was NOT held back, so it is stuck, not pinned.
        let scopes = vec![
            ScopePending {
                pending: vec![],
                masked: vec!["org.example.App".to_string()],
            },
            ScopePending {
                pending: vec!["org.example.App".to_string()],
                masked: vec![],
            },
        ];
        let outcome = diagnose_flatpak_completion(1, "", &scopes).unwrap_err();
        assert!(outcome.contains("Stuck apps: org.example.App."));
    }

    #[test]
    fn diagnose_without_pending_ids_falls_back_to_the_count() {
        // The recount said 2 remain but the diagnosis scan found none
        // (state changed between the two reads): still an honest failure
        // naming the count, never a false success.
        let outcome = diagnose_flatpak_completion(2, "", &[]).unwrap_err();
        assert!(outcome.contains("2 app updates remain"));
    }

    #[test]
    fn pending_count_argv_counts_apps_only() {
        let argv = remote_ls_updates_argv("--user");
        assert!(argv.iter().any(|arg| arg == "--app"));
        assert!(argv.iter().any(|arg| arg == "--updates"));
        assert!(argv.iter().any(|arg| arg == "--user"));
    }

    #[test]
    fn masked_id_parser_skips_comments_and_branches() {
        let ids = parse_masked_ids("# comment\norg.example.App stable\n\norg.example.Other\n");
        assert_eq!(ids, vec!["org.example.App", "org.example.Other"]);
    }

    #[test]
    fn every_availability_error_has_a_blocking_reason() {
        let status = error_status("registry unavailable");
        assert_eq!(status.state, "error");
        assert_eq!(status.detail, status.blocked_reason);
    }
}
