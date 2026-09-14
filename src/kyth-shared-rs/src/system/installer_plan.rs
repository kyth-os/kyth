//! Native port of the `kyth_installer.plan_types` data contract.
//!
//! These are the immutable inputs the destructive install phases consume:
//! the validated request, the storage plan, the resolved plan binding them
//! to an image source, and the dry-run report the UI previews. Execution
//! (validation, commit, partitioning) stays in Python; this module owns the
//! shape so Rust readers — diagnostics, Hub status, future native phases —
//! decode exactly what Python wrote. Field names and defaults mirror the
//! Python dataclasses; `tests/fixtures/installer_plan.json` is decoded on
//! both sides to pin the parity.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Validated, immutable input for one installation attempt. Mirrors
/// `kyth_installer.context.InstallRequest` (which `plan_types` reuses).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct InstallRequest {
    pub disk: String,
    pub install_mode: String,
    pub target_partition: String,
    pub resize_partition: String,
    pub resize_gib: i64,
    pub free_region_start: i64,
    pub free_region_end: i64,
    pub efi_partition: String,
    pub hostname: String,
    pub timezone: String,
    pub locale: String,
    pub keymap: String,
    pub username: String,
    pub password_hash: String,
    pub kernel: String,
    pub mok_password: String,
}

impl Default for InstallRequest {
    fn default() -> Self {
        Self {
            disk: String::new(),
            install_mode: "wipe".into(),
            target_partition: String::new(),
            resize_partition: String::new(),
            resize_gib: 0,
            free_region_start: 0,
            free_region_end: 0,
            efi_partition: String::new(),
            hostname: "kyth".into(),
            timezone: "UTC".into(),
            locale: "en_US.UTF-8".into(),
            keymap: "us".into(),
            username: String::new(),
            password_hash: String::new(),
            kernel: "fedora".into(),
            mok_password: String::new(),
        }
    }
}

impl InstallRequest {
    /// Mirror of `InstallRequest.from_state`: unknown keys are ignored and
    /// missing keys keep defaults, so an older or newer writer cannot break
    /// the reader.
    pub fn from_map(values: &HashMap<String, serde_json::Value>) -> Self {
        let mut request = Self::default();
        let text = |key: &str| {
            values
                .get(key)
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default()
        };
        let number = |key: &str| {
            values
                .get(key)
                .and_then(serde_json::Value::as_i64)
                .unwrap_or(0)
        };
        request.disk = text("disk").into();
        if !text("install_mode").is_empty() {
            request.install_mode = text("install_mode").into();
        }
        request.target_partition = text("target_partition").into();
        request.resize_partition = text("resize_partition").into();
        request.resize_gib = number("resize_gib");
        request.free_region_start = number("free_region_start");
        request.free_region_end = number("free_region_end");
        request.efi_partition = text("efi_partition").into();
        if !text("hostname").is_empty() {
            request.hostname = text("hostname").into();
        }
        if !text("timezone").is_empty() {
            request.timezone = text("timezone").into();
        }
        if !text("locale").is_empty() {
            request.locale = text("locale").into();
        }
        if !text("keymap").is_empty() {
            request.keymap = text("keymap").into();
        }
        request.username = text("username").into();
        request.password_hash = text("password_hash").into();
        if !text("kernel").is_empty() {
            request.kernel = text("kernel").into();
        }
        request.mok_password = text("mok_password").into();
        request
    }
}

/// Storage half of a resolved plan. Mirrors `InstallPlan`.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct InstallPlan {
    pub mode: String,
    pub disk: Option<String>,
    pub target_partition: Option<String>,
}

/// Complete immutable input consumed by destructive install phases.
/// Mirrors `ResolvedInstallPlan`, including the `disk` accessor raising
/// when no target disk resolved.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct ResolvedInstallPlan {
    pub request: InstallRequest,
    pub storage: InstallPlan,
    pub source_ref: String,
    pub target_ref: String,
    pub source_digest: String,
    pub source_kind: String,
    pub source_verified: bool,
}

impl Default for ResolvedInstallPlan {
    fn default() -> Self {
        Self {
            request: InstallRequest::default(),
            storage: InstallPlan::default(),
            source_ref: String::new(),
            target_ref: String::new(),
            source_digest: String::new(),
            source_kind: "network".into(),
            source_verified: false,
        }
    }
}

impl ResolvedInstallPlan {
    pub fn mode(&self) -> &str {
        &self.storage.mode
    }

    /// Mirrors the Python property: an empty disk is a plan-resolution
    /// error, not an empty string.
    pub fn disk(&self) -> Result<&str, String> {
        self.storage
            .disk
            .as_deref()
            .filter(|disk| !disk.is_empty())
            .ok_or_else(|| "Resolved install plan has no target disk".to_string())
    }

    pub fn target_partition(&self) -> &str {
        self.storage.target_partition.as_deref().unwrap_or("")
    }

    pub fn efi_partition(&self) -> &str {
        &self.request.efi_partition
    }

    pub fn kernel(&self) -> &str {
        &self.request.kernel
    }
}

/// Dry-run / validate-only report. Mirrors `PlanReport`; safe for UI
/// preview because producing it never mutates a disk.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct PlanReport {
    pub valid: bool,
    pub mode: String,
    pub disk: String,
    pub target_partition: String,
    pub efi_partition: String,
    pub will_create_partition: bool,
    pub will_shrink_filesystem: bool,
    pub required_bytes: u64,
    pub available_bytes: u64,
    pub is_gpt: bool,
    pub needs_bios_boot: bool,
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn fixture() -> serde_json::Value {
        let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../tests/fixtures/installer_plan.json");
        let raw = std::fs::read_to_string(&path).expect("installer_plan fixture exists");
        serde_json::from_str(&raw).expect("fixture is valid JSON")
    }

    #[test]
    fn report_decodes_the_shared_fixture() {
        let report: PlanReport =
            serde_json::from_value(fixture()["report"].clone()).expect("report decodes");
        assert!(report.valid);
        assert_eq!(report.mode, "guided");
        assert_eq!(report.disk, "/dev/nvme0n1");
        assert_eq!(report.required_bytes, 34_359_738_368);
        assert!(report.available_bytes > report.required_bytes);
        assert!(report.is_gpt);
        assert!(!report.needs_bios_boot);
        assert!(report.errors.is_empty());
        assert_eq!(report.warnings, ["Windows partition will shrink"]);
    }

    #[test]
    fn resolved_plan_accessors_match_python_semantics() {
        let plan: ResolvedInstallPlan =
            serde_json::from_value(fixture()["plan"].clone()).expect("plan decodes");
        assert_eq!(plan.mode(), "guided");
        assert_eq!(plan.disk().unwrap(), "/dev/nvme0n1");
        assert_eq!(plan.target_partition(), "/dev/nvme0n1p3");
        assert_eq!(plan.efi_partition(), "/dev/nvme0n1p1");
        assert_eq!(plan.kernel(), "fedora");
        assert_eq!(plan.source_kind, "network");
        assert!(plan.source_verified);
        // Round-trips: what Rust writes, Python must read back unchanged.
        let encoded = serde_json::to_value(&plan).expect("plan serializes");
        let decoded: ResolvedInstallPlan =
            serde_json::from_value(encoded).expect("plan re-decodes");
        assert_eq!(decoded, plan);
    }

    #[test]
    fn disk_accessor_rejects_an_unresolved_plan() {
        let mut plan = ResolvedInstallPlan::default();
        assert_eq!(
            plan.disk().unwrap_err(),
            "Resolved install plan has no target disk"
        );
        plan.storage.disk = Some(String::new());
        assert!(plan.disk().is_err());
        plan.storage.disk = Some("/dev/sda".into());
        assert_eq!(plan.disk().unwrap(), "/dev/sda");
    }

    #[test]
    fn from_map_ignores_unknown_keys_and_keeps_defaults() {
        let values: HashMap<String, serde_json::Value> = [
            ("disk".to_string(), serde_json::json!("/dev/sda")),
            ("username".to_string(), serde_json::json!("pat")),
            ("future_field".to_string(), serde_json::json!(true)),
        ]
        .into_iter()
        .collect();
        let request = InstallRequest::from_map(&values);
        assert_eq!(request.disk, "/dev/sda");
        assert_eq!(request.username, "pat");
        // Untouched fields keep Python's defaults, not empty strings.
        assert_eq!(request.install_mode, "wipe");
        assert_eq!(request.hostname, "kyth");
        assert_eq!(request.kernel, "fedora");
    }
}
