//! Pure Secure Boot/MOK decision model.
//!
//! No password, certificate contents, firmware access, or subprocess result
//! is handled here. The Python service performs those privileged operations
//! and feeds their bounded observations into the same state model.

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize)]
pub(crate) struct SecureBootInput {
    #[serde(default = "default_kernel")]
    pub kernel: String,
    #[serde(default)]
    pub force_stage: bool,
    #[serde(default)]
    pub certificate_present: bool,
    #[serde(default)]
    pub mokutil_present: bool,
    #[serde(default = "default_unknown")]
    pub secure_boot: String,
    #[serde(default = "default_unknown")]
    pub enrolled: String,
    #[serde(default = "default_unknown")]
    pub pending: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(crate) struct SecureBootPlan {
    pub state: String,
    pub action: String,
    pub requires_password: bool,
    pub requires_reboot_confirmation: bool,
    pub message: String,
    pub executor: &'static str,
}

fn default_kernel() -> String { "fedora".to_string() }
fn default_unknown() -> String { "unknown".to_string() }

pub(crate) fn build_plan(input: SecureBootInput) -> Result<SecureBootPlan, String> {
    let kernel = input.kernel.trim().to_ascii_lowercase();
    let secure_boot = input.secure_boot.trim().to_ascii_lowercase();
    let enrolled = input.enrolled.trim().to_ascii_lowercase();
    let pending = input.pending.trim().to_ascii_lowercase();
    if !matches!(kernel.as_str(), "fedora" | "cachy") {
        return Err(format!("unsupported kernel flavor: {kernel}"));
    }
    let skipped = |message: &str| SecureBootPlan {
        state: "skipped".to_string(),
        action: "none".to_string(),
        requires_password: false,
        requires_reboot_confirmation: false,
        message: message.to_string(),
        executor: "kyth-installerd",
    };
    if kernel != "cachy" && !input.force_stage {
        return Ok(skipped("standard KythOS kernel does not require custom MOK enrollment"));
    }
    if !input.certificate_present {
        return Ok(skipped("KythOS Secure Boot certificate is not present in the live image"));
    }
    if !input.mokutil_present {
        return Ok(skipped("mokutil is not available in the live image"));
    }
    if secure_boot == "disabled" {
        return Ok(skipped("Secure Boot is disabled; MOK enrollment is not required"));
    }
    if secure_boot != "enabled" {
        return Ok(SecureBootPlan {
            state: "unknown".to_string(),
            action: "probe".to_string(),
            requires_password: false,
            requires_reboot_confirmation: false,
            message: "Secure Boot state must be checked by the privileged service".to_string(),
            executor: "kyth-installerd",
        });
    }
    if enrolled == "yes" {
        return Ok(SecureBootPlan {
            state: "enrolled".to_string(),
            action: "none".to_string(),
            requires_password: false,
            requires_reboot_confirmation: false,
            message: "KythOS Secure Boot key is already enrolled".to_string(),
            executor: "kyth-installerd",
        });
    }
    if pending == "yes" {
        return Ok(SecureBootPlan {
            state: "pending".to_string(),
            action: "none".to_string(),
            requires_password: false,
            requires_reboot_confirmation: true,
            message: "KythOS Secure Boot enrollment is pending confirmation on the next boot".to_string(),
            executor: "kyth-installerd",
        });
    }
    Ok(SecureBootPlan {
        state: "ready".to_string(),
        action: "import-certificate".to_string(),
        requires_password: true,
        requires_reboot_confirmation: true,
        message: "The privileged service may stage KythOS MOK enrollment".to_string(),
        executor: "kyth-installerd",
    })
}

pub(crate) fn classify_import(exit_code: i32) -> &'static str {
    if exit_code == 0 { "staged" } else { "failed" }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cachy() -> SecureBootInput {
        SecureBootInput {
            kernel: "cachy".to_string(),
            force_stage: false,
            certificate_present: true,
            mokutil_present: true,
            secure_boot: "enabled".to_string(),
            enrolled: "no".to_string(),
            pending: "no".to_string(),
        }
    }

    #[test]
    fn plans_import_without_handling_the_password() {
        let plan = build_plan(cachy()).expect("MOK plan should validate");
        assert_eq!(plan.action, "import-certificate");
        assert!(plan.requires_password);
        assert!(plan.requires_reboot_confirmation);
        assert!(!plan.message.contains("password"));
    }

    #[test]
    fn classifies_existing_states_and_non_custom_kernel() {
        assert_eq!(build_plan(SecureBootInput { kernel: "fedora".to_string(), ..cachy() }).unwrap().state, "skipped");
        assert_eq!(build_plan(SecureBootInput { enrolled: "yes".to_string(), ..cachy() }).unwrap().state, "enrolled");
        assert_eq!(build_plan(SecureBootInput { pending: "yes".to_string(), ..cachy() }).unwrap().state, "pending");
        assert_eq!(classify_import(0), "staged");
        assert_eq!(classify_import(1), "failed");
    }

    #[test]
    fn matches_shared_decision_fixture() {
        #[derive(Deserialize)]
        struct Case {
            input: SecureBootInput,
            expected: Expected,
        }
        #[derive(Deserialize)]
        struct Expected {
            state: String,
            action: String,
        }

        let cases: Vec<Case> = serde_json::from_str(include_str!("../testdata/secure_boot_cases.json"))
            .expect("secure boot fixture should be valid");
        for case in cases {
            let plan = build_plan(case.input).expect("fixture input should validate");
            assert_eq!(plan.state, case.expected.state);
            assert_eq!(plan.action, case.expected.action);
        }
    }
}
