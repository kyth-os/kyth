//! Typed contract for the root-owned installer executor.
//!
//! This is intentionally an operation-level contract, never an arbitrary
//! command bridge. The Tauri shell can construct and inspect these plans;
//! only kyth-installerd may execute them after repeating authoritative
//! validation against live storage and firmware state.

use serde::{Deserialize, Serialize};

use crate::installer_accounts::{self, CreateUserInput};
use crate::installer_bootc::{self, BootcInstallInput, BootcInstallPlan};
use crate::installer_configuration::{self, ConfigurationInput, ConfigurationPlan};
use crate::installer_secure_boot::{self, SecureBootInput, SecureBootPlan};

pub(crate) const EXECUTOR_PROTOCOL_VERSION: u32 = 1;

#[derive(Clone, Debug, Deserialize)]
pub(crate) struct InstallerExecutionInput {
    pub bootc: BootcInstallInput,
    pub configuration: ConfigurationInput,
    pub secure_boot: SecureBootInput,
    #[serde(default)]
    pub account: Option<CreateUserInput>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(crate) struct AccountCreationPlan {
    pub deploy_root: String,
    pub target_root: String,
    pub username: String,
    pub executor: &'static str,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(crate) struct InstallerExecutionPlan {
    pub protocol_version: u32,
    pub executor: &'static str,
    pub bootc: BootcInstallPlan,
    pub configuration: ConfigurationPlan,
    pub account: Option<AccountCreationPlan>,
    pub secure_boot: SecureBootPlan,
}

pub(crate) fn build_plan(input: InstallerExecutionInput) -> Result<InstallerExecutionPlan, String> {
    let account = match input.account {
        Some(account) => {
            let (deploy_root, target_root) = installer_accounts::validate(&account)?;
            Some(AccountCreationPlan {
                deploy_root: deploy_root.to_string_lossy().into_owned(),
                target_root: target_root.to_string_lossy().into_owned(),
                username: account.username.trim().to_string(),
                executor: "kyth-installer-exec",
            })
        }
        None => None,
    };
    Ok(InstallerExecutionPlan {
        protocol_version: EXECUTOR_PROTOCOL_VERSION,
        executor: "kyth-installerd",
        bootc: installer_bootc::build_plan(input.bootc)?,
        configuration: installer_configuration::build_plan(input.configuration)?,
        account,
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
            account: None,
        })
        .expect("execution plan should validate");
        assert_eq!(plan.protocol_version, 1);
        assert_eq!(plan.executor, "kyth-installerd");
        assert!(plan.bootc.destructive);
        assert_eq!(plan.secure_boot.state, "skipped");
        assert!(plan.account.is_none());
    }

    #[test]
    fn account_plan_excludes_password_hash() {
        let account = CreateUserInput {
            deploy_root: "/mnt/deploy".into(),
            target_root: "/mnt/target".into(),
            username: "kyth_user".into(),
            password_hash: "$6$must-not-be-planned".into(),
        };
        let plan = build_plan(InstallerExecutionInput {
            bootc: BootcInstallInput {
                subcommand: "to-disk".into(),
                source_imgref: "oci:/image".into(),
                target_imgref: "kyth:latest".into(),
                target: "/dev/sda".into(),
                skip_fetch_check: true,
                skip_finalize: false,
                root_subvolume: false,
                wipe: true,
            },
            configuration: ConfigurationInput {
                target_root: "/mnt/target".into(),
                hostname: "kyth".into(),
                timezone: "UTC".into(),
                locale: "en_US.UTF-8".into(),
                keymap: "us".into(),
            },
            account: Some(account),
            secure_boot: SecureBootInput {
                kernel: "fedora".into(),
                force_stage: false,
                certificate_present: false,
                mokutil_present: false,
                secure_boot: "unknown".into(),
                enrolled: "unknown".into(),
                pending: "unknown".into(),
            },
        })
        .expect("execution plan should validate");
        let encoded = serde_json::to_string(&plan.account).unwrap();
        assert!(!encoded.contains("must-not-be-planned"));
        assert!(encoded.contains("kyth_user"));
    }
}
