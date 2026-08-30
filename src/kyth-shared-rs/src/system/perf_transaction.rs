//! Pure planning and result handling for a performance-profile transaction.
//!
//! Backup copying and `sysctl` execution remain caller-owned because they are
//! privileged filesystem/process operations. Rust callers can share the exact
//! command and rollback policy.

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PerfTransactionPlan {
    pub profile: String,
    pub dry_run: bool,
    pub backup_pattern: String,
    pub dry_run_command: Vec<String>,
    pub rollback_on_apply_failure: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PerfTransactionResult {
    pub success: bool,
    pub rollback_required: bool,
    pub message: String,
}

pub fn plan(profile: impl Into<String>, dry_run: bool) -> PerfTransactionPlan {
    PerfTransactionPlan {
        profile: profile.into(),
        dry_run,
        backup_pattern: "/etc/sysctl.d/99-kyth*.conf".into(),
        dry_run_command: vec!["sysctl".into(), "--system".into(), "--dry-run".into()],
        rollback_on_apply_failure: true,
    }
}

/// Evaluate bounded command results: a failed dry run aborts without rollback,
/// while a failed apply requests restoration of the captured configuration.
pub fn evaluate(
    dry_run: bool,
    dry_run_exit: Option<i32>,
    apply_exit: Option<i32>,
) -> PerfTransactionResult {
    if dry_run_exit.is_some_and(|code| code != 0) {
        return PerfTransactionResult {
            success: false,
            rollback_required: false,
            message: "sysctl --system --dry-run failed".into(),
        };
    }
    if dry_run {
        return PerfTransactionResult {
            success: true,
            rollback_required: false,
            message: "dry-run ok".into(),
        };
    }
    if apply_exit.is_some_and(|code| code != 0) {
        return PerfTransactionResult {
            success: false,
            rollback_required: true,
            message: "profile apply failed; restore the configuration backup".into(),
        };
    }
    PerfTransactionResult {
        success: true,
        rollback_required: false,
        message: "profile applied".into(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plan_preserves_profile_and_safe_command_shape() {
        let value = plan("gaming", false);
        assert_eq!(value.profile, "gaming");
        assert_eq!(value.dry_run_command, ["sysctl", "--system", "--dry-run"]);
        assert!(value.rollback_on_apply_failure);
    }

    #[test]
    fn evaluation_distinguishes_dry_run_and_apply_failures() {
        assert!(evaluate(true, Some(0), None).success);
        let dry_failure = evaluate(true, Some(1), None);
        assert!(!dry_failure.success);
        assert!(!dry_failure.rollback_required);
        let apply_failure = evaluate(false, Some(0), Some(1));
        assert!(!apply_failure.success);
        assert!(apply_failure.rollback_required);
    }
}
