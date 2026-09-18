//! Pure bootc install-command planning.
//!
//! This module deliberately constructs an operation description instead of
//! spawning bootc. The root-owned Rust daemon and its typed helper are the
//! only executors; the unprivileged shell can use this plan for preflight.

use serde::{Deserialize, Serialize};

fn default_true() -> bool {
    true
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub(crate) struct BootcInstallInput {
    pub subcommand: String,
    pub source_imgref: String,
    pub target_imgref: String,
    pub target: String,
    #[serde(default = "default_true")]
    pub skip_fetch_check: bool,
    #[serde(default)]
    pub skip_finalize: bool,
    #[serde(default)]
    pub root_subvolume: bool,
    #[serde(default)]
    pub wipe: bool,
    /// Requested root-device encryption for `to-disk` installs.
    ///
    /// Accepted values are `"none"` (explicit plaintext, the default) and
    /// `"tpm2"` (TPM2-bound LUKS via `bootc install to-disk --block-setup
    /// tpm2-luks`). Any other value fails closed: the installer must never
    /// silently fall back to plaintext when encryption was requested.
    #[serde(default)]
    pub encryption: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(crate) struct BootcInstallPlan {
    pub subcommand: String,
    pub argv: Vec<String>,
    pub target: String,
    pub destructive: bool,
    pub requires_network: bool,
    pub executor: &'static str,
}

fn safe_reference(value: &str, label: &str) -> Result<String, String> {
    let value = value.trim();
    if value.is_empty() || value.len() > 4096 || value.contains("..") {
        return Err(format!("{label} is empty or unsafe."));
    }
    if !value.bytes().all(|byte| {
        byte.is_ascii_alphanumeric()
            || matches!(byte, b'.' | b'/' | b'_' | b'@' | b':' | b'+' | b'-')
    }) {
        return Err(format!("{label} contains unsupported characters."));
    }
    Ok(value.to_string())
}

fn safe_absolute_path(value: &str, label: &str) -> Result<String, String> {
    let value = value.trim();
    if !value.starts_with('/') || value.len() > 4096 || value.contains("..") {
        return Err(format!("{label} must be an absolute safe path."));
    }
    if !value.bytes().all(|byte| {
        byte.is_ascii_alphanumeric() || matches!(byte, b'/' | b'.' | b'_' | b'+' | b':' | b'-')
    }) {
        return Err(format!("{label} contains unsupported characters."));
    }
    Ok(value.to_string())
}

pub(crate) fn build_plan(input: BootcInstallInput) -> Result<BootcInstallPlan, String> {
    let subcommand = input.subcommand.trim().to_ascii_lowercase();
    if !matches!(subcommand.as_str(), "to-disk" | "to-filesystem") {
        return Err(format!(
            "unsupported bootc install subcommand: {subcommand}"
        ));
    }
    let source_imgref = safe_reference(&input.source_imgref, "source image reference")?;
    let target_imgref = safe_reference(&input.target_imgref, "target image reference")?;
    let encryption = input.encryption.trim().to_ascii_lowercase();
    if !matches!(encryption.as_str(), "" | "none" | "tpm2") {
        return Err(format!(
            "encryption unsupported: '{encryption}' is not a supported encryption mode (expected 'none' or 'tpm2')."
        ));
    }
    let target = if subcommand == "to-disk" {
        crate::installer_plan::normalize_device_path(&input.target)
            .ok_or_else(|| "bootc disk target must be a safe device path.".to_string())?
    } else {
        safe_absolute_path(&input.target, "bootc filesystem target")?
    };

    let mut argv = vec![
        "bootc".to_string(),
        "install".to_string(),
        subcommand.clone(),
        "--source-imgref".to_string(),
        source_imgref.clone(),
        "--target-imgref".to_string(),
        target_imgref,
    ];
    if subcommand == "to-filesystem" {
        // `to-filesystem` writes into an already-prepared mountpoint, so
        // bootc offers no block-setup knob there. Refuse encryption rather
        // than silently installing plaintext.
        if encryption == "tpm2" {
            return Err(
                "encryption unsupported for bootc to-filesystem installs: encryption requires a to-disk install."
                    .to_string(),
            );
        }
        argv.push("--acknowledge-destructive".to_string());
        if input.skip_finalize {
            argv.push("--skip-finalize".to_string());
        }
        if input.root_subvolume {
            argv.push("--karg=rootflags=subvol=@".to_string());
        }
    } else {
        argv.extend(["--filesystem".to_string(), "btrfs".to_string()]);
        // The requested encryption mode is always explicit on the bootc
        // command line: `direct` for plaintext, `tpm2-luks` for TPM2-bound
        // LUKS. Plaintext is therefore a deliberate choice, never a silent
        // fallback when encryption was requested.
        match encryption.as_str() {
            "" | "none" => {
                argv.extend(["--block-setup".to_string(), "direct".to_string()]);
            }
            "tpm2" => {
                argv.extend(["--block-setup".to_string(), "tpm2-luks".to_string()]);
            }
            _ => unreachable!("encryption modes are validated above"),
        }
        if input.wipe {
            argv.push("--wipe".to_string());
        }
    }
    if input.skip_fetch_check && !argv.iter().any(|arg| arg == "--skip-fetch-check") {
        argv.push("--skip-fetch-check".to_string());
    }
    argv.push(target.clone());

    Ok(BootcInstallPlan {
        subcommand,
        argv,
        target,
        destructive: true,
        // --skip-fetch-check bypasses the reachability preflight only; a
        // docker:// source still needs the network when bootc executes.
        requires_network: source_imgref.starts_with("docker://"),
        executor: "kyth-installerd",
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn input(subcommand: &str) -> BootcInstallInput {
        BootcInstallInput {
            subcommand: subcommand.to_string(),
            source_imgref: "docker://ghcr.io/kyth-os/kyth:latest".to_string(),
            target_imgref: "ghcr.io/kyth-os/kyth:latest".to_string(),
            target: "/dev/sda".to_string(),
            skip_fetch_check: true,
            skip_finalize: false,
            root_subvolume: false,
            wipe: false,
            encryption: "none".to_string(),
        }
    }

    #[test]
    fn builds_disk_install_without_arbitrary_flags() {
        let plan = build_plan(BootcInstallInput {
            wipe: true,
            ..input("to-disk")
        })
        .expect("disk plan should validate");
        assert_eq!(plan.argv[..3], ["bootc", "install", "to-disk"]);
        assert!(plan
            .argv
            .windows(2)
            .any(|pair| pair == ["--filesystem", "btrfs"]));
        assert!(plan.argv.iter().any(|arg| arg == "--wipe"));
        assert!(plan.requires_network);
    }

    #[test]
    fn builds_filesystem_install_with_safe_bootc_flags() {
        let plan = build_plan(BootcInstallInput {
            target: "/mnt/kyth".to_string(),
            skip_fetch_check: false,
            skip_finalize: true,
            root_subvolume: true,
            ..input("to-filesystem")
        })
        .expect("filesystem plan should validate");
        assert!(plan
            .argv
            .iter()
            .any(|arg| arg == "--acknowledge-destructive"));
        assert!(plan.argv.iter().any(|arg| arg == "--skip-finalize"));
        assert!(plan
            .argv
            .iter()
            .any(|arg| arg == "--karg=rootflags=subvol=@"));
        assert!(plan.requires_network);
    }

    #[test]
    fn rejects_unsafe_targets_and_references() {
        for target in ["../../etc", "relative", "/mnt/with space"] {
            let error = build_plan(BootcInstallInput {
                target: target.to_string(),
                ..input("to-filesystem")
            })
            .expect_err("unsafe target must fail");
            assert!(error.contains("target"), "{error}");
        }
        let error = build_plan(BootcInstallInput {
            source_imgref: "docker://example/$(touch /tmp/pwned)".to_string(),
            ..input("to-disk")
        })
        .expect_err("unsafe image reference must fail");
        assert!(error.contains("image reference"));
    }

    #[test]
    fn encryption_defaults_to_explicit_plaintext_block_setup() {
        let plan = build_plan(input("to-disk")).expect("disk plan should validate");
        assert!(plan
            .argv
            .windows(2)
            .any(|pair| pair == ["--block-setup", "direct"]));
        assert!(!plan
            .argv
            .windows(2)
            .any(|pair| pair == ["--block-setup", "tpm2-luks"]));
    }

    #[test]
    fn tpm2_encryption_selects_tpm2_luks_block_setup() {
        let plan = build_plan(BootcInstallInput {
            encryption: "tpm2".to_string(),
            wipe: true,
            ..input("to-disk")
        })
        .expect("tpm2 disk plan should validate");
        assert!(plan
            .argv
            .windows(2)
            .any(|pair| pair == ["--block-setup", "tpm2-luks"]));
        assert!(!plan
            .argv
            .windows(2)
            .any(|pair| pair == ["--block-setup", "direct"]));
    }

    #[test]
    fn unknown_encryption_fails_closed_instead_of_plaintext() {
        for mode in ["luks", "tpm", "aes-256", "yes"] {
            let error = build_plan(BootcInstallInput {
                encryption: mode.to_string(),
                ..input("to-disk")
            })
            .expect_err("unknown encryption mode must fail closed");
            assert!(
                error.contains("encryption unsupported"),
                "unexpected error: {error}"
            );
        }
    }

    #[test]
    fn filesystem_install_cannot_honor_encryption() {
        let error = build_plan(BootcInstallInput {
            encryption: "tpm2".to_string(),
            target: "/mnt/kyth".to_string(),
            ..input("to-filesystem")
        })
        .expect_err("to-filesystem cannot honor encryption");
        assert!(
            error.contains("encryption unsupported"),
            "unexpected error: {error}"
        );
    }
}
