//! Typed contract for the root-owned installer executor.
//!
//! This is intentionally an operation-level contract, never an arbitrary
//! command bridge. The Tauri shell can construct and inspect these plans;
//! only kyth-installerd may execute them after repeating authoritative
//! validation against live storage and firmware state.

use serde::{Deserialize, Serialize};

use crate::installer_bootc::{self, BootcInstallInput, BootcInstallPlan};
use crate::installer_configuration::{self, ConfigurationInput, ConfigurationPlan};
use crate::installer_secure_boot::{self, SecureBootInput, SecureBootPlan};

pub(crate) const EXECUTOR_PROTOCOL_VERSION: u32 = 1;

#[derive(Clone, Debug, Deserialize)]
pub(crate) struct InstallerExecutionInput {
    pub bootc: BootcInstallInput,
    pub configuration: ConfigurationInput,
    pub secure_boot: SecureBootInput,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(crate) struct InstallerExecutionPlan {
    pub protocol_version: u32,
    pub executor: &'static str,
    pub bootc: BootcInstallPlan,
    pub configuration: ConfigurationPlan,
    pub secure_boot: SecureBootPlan,
}

pub(crate) fn build_plan(input: InstallerExecutionInput) -> Result<InstallerExecutionPlan, String> {
    Ok(InstallerExecutionPlan {
        protocol_version: EXECUTOR_PROTOCOL_VERSION,
        executor: "kyth-installerd",
        bootc: installer_bootc::build_plan(input.bootc)?,
        configuration: installer_configuration::build_plan(input.configuration)?,
        secure_boot: installer_secure_boot::build_plan(input.secure_boot)?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn produces_one_explicit_privileged_operation_contract() {
        let plan = build_plan(InstallerExecutionInput {
            bootc: BootcInstallInput {
                subcommand: "to-disk".to_string(),
                source_imgref: "oci:/usr/share/kyth/image:latest".to_string(),
                target_imgref: "ghcr.io/kyth-os/kyth:latest".to_string(),
                target: "/dev/sda".to_string(),
                skip_fetch_check: true,
                skip_finalize: false,
                root_subvolume: false,
                wipe: true,
            },
            configuration: ConfigurationInput {
                target_root: "/mnt/target".to_string(),
                hostname: "kyth".to_string(),
                timezone: "UTC".to_string(),
                locale: "en_US.UTF-8".to_string(),
                keymap: "us".to_string(),
            },
            secure_boot: SecureBootInput {
                kernel: "fedora".to_string(),
                force_stage: false,
                certificate_present: false,
                mokutil_present: false,
                secure_boot: "unknown".to_string(),
                enrolled: "unknown".to_string(),
                pending: "unknown".to_string(),
            },
        }).expect("execution plan should validate");
        assert_eq!(plan.protocol_version, 1);
        assert_eq!(plan.executor, "kyth-installerd");
        assert!(plan.bootc.destructive);
        assert_eq!(plan.secure_boot.state, "skipped");
    }
}
