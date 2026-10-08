//! Native production executor between the job supervisor and typed operations.
//!
//! It accepts a complete typed request, validates it through the plan
//! builders, and retains only the resulting non-secret plans. Every phase is
//! either implemented by Rust or a fixed, typed root-only helper operation;
//! there is no Python whole-install worker or generic command/filesystem
//! bridge.

use std::collections::HashSet;
use std::fmt;
use std::path::{Component, Path, PathBuf};
use std::process::Command;
use std::sync::Mutex;

use super::installer_durable_journal::{DurableJournal, OpState, JOURNAL_FILE_NAME};

// systemd creates this parent as root-owned and non-writable by the live user.
// A fixed staging path under /var/tmp could be pre-created as a symlink before
// the privileged installer mounts the selected target there.
const BTRFS_STAGING_MOUNTPOINT: &str = "/run/kyth-installer/btrfs-root";
const WIPE_STAGING_MOUNTPOINT: &str = "/run/kyth-installer/install-root";
const FILESYSTEM_STAGING_MOUNTPOINT: &str = "/run/kyth-installer/alongside-target";

use super::installer_executor::{self, InstallerExecutionInput, InstallerExecutionPlan};
use super::installer_job::{CancellationToken, JobSupervisor, PhaseExecutor};
use super::installer_plan::{self, InstallerPlan, InstallerPlanInput};
use super::installer_runtime::Phase;
use crate::installer_configuration;

/// The complete typed request accepted by the native phase adapter.
///
/// The storage request and executor request intentionally remain separate:
/// the former describes the selected install mode, while the latter contains
/// the typed bootc, configuration, account, and Secure Boot inputs.
pub(crate) struct NativeInstallRequest {
    pub storage: InstallerPlanInput,
    pub execution: InstallerExecutionInput,
    pub manual_mounts: Option<crate::installer_manual::ManualMountsInput>,
    pub secure_boot_password: String,
    pub transaction_path: String,
}

fn normalize_kernel_flavor(value: &str) -> String {
    let normalized = value.trim().to_ascii_lowercase();
    if normalized == "cachyos" {
        "cachy".to_string()
    } else {
        normalized
    }
}

/// Install modes whose storage phase formats a Btrfs target with `@` and
/// `@home` subvolumes (`prepare_btrfs_target`), so configuration must mount
/// `@home` at /var/home and persist it in fstab. Python rewrote free_space
/// and resize_ntfs to "alongside" after partitioning, so all three share the
/// alongside-home step; manual installs configure /home via manual mounts.
fn lays_out_home_subvolume(mode: &str) -> bool {
    matches!(mode, "alongside" | "free_space" | "resize_ntfs")
}

/// Disk-helper request that mounts the target ESP at `mountpoint`. An ESP the
/// live session already has mounted is bind-mounted from that mountpoint:
/// the helper keys bind mounts on the `bind` field, and without it treats the
/// mountpoint path as a device, which its `/dev/` device gate rejects.
fn efi_mount_operation(
    efi: &crate::installer_storage::EfiPartition,
    mountpoint: &str,
) -> serde_json::Value {
    match &efi.mounted_at {
        Some(source) => serde_json::json!({
            "operation": "mount_filesystem",
            "device": source,
            "mountpoint": mountpoint,
            "bind": true
        }),
        None => serde_json::json!({
            "operation": "mount_filesystem",
            "device": efi.name,
            "mountpoint": mountpoint
        }),
    }
}

impl NativeInstallRequest {
    /// Decode the flat HTTP representation used by the existing frontend.
    /// Secrets are consumed into the typed request and never serialized back.
    pub(crate) fn from_http(value: serde_json::Value) -> Result<Self, String> {
        let object = value
            .as_object()
            .ok_or_else(|| "installer start request must be a JSON object".to_string())?;
        let text = |name: &str, default: &str| {
            object
                .get(name)
                .and_then(serde_json::Value::as_str)
                .unwrap_or(default)
                .to_string()
        };
        let number = |name: &str| {
            object
                .get(name)
                .and_then(serde_json::Value::as_i64)
                .unwrap_or(0)
        };
        let flag = |name: &str, default: bool| {
            object
                .get(name)
                .and_then(serde_json::Value::as_bool)
                .unwrap_or(default)
        };
        // The irreversible acknowledgement is a daemon-side gate, not just a
        // frontend checkbox: the Slint shell sends `acknowledged-irreversible`
        // and the web frontend sends `acknowledged_irreversible`. A start
        // request without either must fail closed before any worker starts.
        let acknowledged = object
            .get("acknowledged-irreversible")
            .and_then(serde_json::Value::as_bool)
            .or_else(|| {
                object
                    .get("acknowledged_irreversible")
                    .and_then(serde_json::Value::as_bool)
            })
            .unwrap_or(false);
        if !acknowledged {
            return Err("installation cannot start until the irreversible step is acknowledged: once partitioning starts, erased or resized data cannot be restored."
                .to_string());
        }
        let username = text("username", "").trim().to_string();
        let password_hash = {
            let supplied_hash = text("password_hash", "");
            if supplied_hash.is_empty() && !username.is_empty() {
                crate::installer_accounts::hash_password(&text("password", ""))?
            } else {
                supplied_hash
            }
        };
        // L3: an absent install mode must fail closed in plan validation
        // (installer_plan.rs rejects the empty mode) instead of silently
        // defaulting to "wipe" and full-disk-erasing on a malformed request.
        let install_mode = text("install_mode", "").to_ascii_lowercase();
        let filesystem_install = matches!(
            install_mode.as_str(),
            "alongside" | "manual" | "free_space" | "resize_ntfs"
        );
        // Implied by the mode, never a separate request key: bootc to-disk
        // refuses a partitioned disk without --wipe, and no frontend sends
        // one. Filesystem installs never wipe the disk.
        let erase_disk = install_mode == "wipe";
        let target_root = if filesystem_install {
            FILESYSTEM_STAGING_MOUNTPOINT.to_string()
        } else {
            WIPE_STAGING_MOUNTPOINT.to_string()
        };
        let manual_mounts = if install_mode == "manual" {
            let mounts = object
                .get("mounts")
                .cloned()
                .unwrap_or_else(|| serde_json::json!([]));
            // M4: the manual-mounts apply call takes a request uuid (validated
            // by installer_manual.rs once its input struct gains the field);
            // plumb it through here and reject an empty one now.
            let mounts_uuid = text("uuid", "");
            if mounts_uuid.trim().is_empty() {
                return Err("manual install request must include a non-empty uuid".to_string());
            }
            Some(
                serde_json::from_value(serde_json::json!({
                    "config_root": target_root.clone(),
                    "fstab_path": format!("{target_root}/etc/fstab"),
                    "mounts": mounts,
                    "uuid": mounts_uuid,
                }))
                .map_err(|error| format!("invalid manual mount request: {error}"))?,
            )
        } else {
            None
        };
        let account =
            (!username.is_empty()).then_some(crate::installer_accounts::CreateUserInput {
                deploy_root: target_root.clone(),
                target_root: target_root.clone(),
                username,
                password_hash,
            });
        // M5: capture the selected disk's identity now, from lsblk, never
        // from the client. Best-effort: a probe failure leaves the fields
        // empty and `verify_disk_identity` treats them as unknown rather
        // than blocking the install.
        let disk = text("disk", "");
        let (target_disk_model, target_disk_serial, target_disk_size_bytes) =
            probe_disk_identity(&disk);
        Ok(Self {
            storage: InstallerPlanInput {
                disk,
                install_mode,
                target_partition: text("target_partition", ""),
                resize_partition: text("resize_partition", ""),
                resize_gib: number("resize_gib"),
                free_region_start: number("free_region_start"),
                free_region_end: number("free_region_end"),
                target_disk_serial,
                target_disk_model,
                target_disk_size_bytes,
            },
            execution: InstallerExecutionInput {
                bootc: crate::installer_bootc::BootcInstallInput {
                    // L17: the subcommand is derived strictly from the
                    // install mode. The old client-controlled `subcommand`
                    // key could smuggle an unexpected subcommand past plan
                    // validation into the bootc argv.
                    subcommand: if filesystem_install {
                        "to-filesystem".to_string()
                    } else {
                        "to-disk".to_string()
                    },
                    source_imgref: std::env::var("KYTH_SOURCE_IMAGE")
                        .unwrap_or_else(|_| "ghcr.io/kyth-os/kyth:latest".to_string()),
                    target_imgref: std::env::var("KYTH_TARGET_IMAGE")
                        .unwrap_or_else(|_| "ghcr.io/kyth-os/kyth:latest".to_string()),
                    target: if filesystem_install {
                        FILESYSTEM_STAGING_MOUNTPOINT.to_string()
                    } else {
                        text("disk", "")
                    },
                    skip_fetch_check: flag("skip_fetch_check", false),
                    // bootc's finalize remounts the target read-only; the
                    // configuration phase still has to write into it.
                    skip_finalize: filesystem_install,
                    root_subvolume: flag("root_subvolume", filesystem_install),
                    wipe: erase_disk,
                    encryption: text("encryption", "none"),
                    tpm_recovery_ack: flag("tpm_recovery_ack", false),
                },
                configuration: crate::installer_configuration::ConfigurationInput {
                    target_root: target_root.clone(),
                    hostname: text("hostname", "kyth"),
                    timezone: text("timezone", "UTC"),
                    locale: text("locale", "en_US.UTF-8"),
                    keymap: text("keymap", "us"),
                },
                account,
                secure_boot: crate::installer_secure_boot::SecureBootInput {
                    kernel: normalize_kernel_flavor(&text("kernel", "fedora")),
                    force_stage: flag("force_stage", false),
                    certificate_present: flag("certificate_present", false),
                    mokutil_present: flag("mokutil_present", false),
                    secure_boot: text("secure_boot", "unknown"),
                    enrolled: text("enrolled", "unknown"),
                    pending: text("pending", "unknown"),
                },
            },
            manual_mounts,
            secure_boot_password: text("mok_password", ""),
            transaction_path: text(
                "transaction_path",
                &std::env::var("KYTH_INSTALLER_TRANSACTION")
                    .unwrap_or_else(|_| "/run/kyth-installer/txn/transaction.json".to_string()),
            ),
        })
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum NativeOperation {
    ValidateStoragePlan,
    ValidateExecutionPlan,
    StorageMutation,
    ImageWrite,
    ConfigurationWrite,
    AccountCreate,
    SecureBootInteraction,
    CompletionCommit,
}

impl fmt::Display for NativeOperation {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        let value = match self {
            Self::ValidateStoragePlan => "validate_storage_plan",
            Self::ValidateExecutionPlan => "validate_execution_plan",
            Self::StorageMutation => "storage_mutation",
            Self::ImageWrite => "image_write",
            Self::ConfigurationWrite => "configuration_write",
            Self::AccountCreate => "account_create",
            Self::SecureBootInteraction => "secure_boot_interaction",
            Self::CompletionCommit => "completion_commit",
        };
        formatter.write_str(value)
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum NativePhaseError {
    Cancelled {
        phase: Phase,
    },
    InvalidPlan {
        phase: Phase,
        operation: NativeOperation,
    },
    Execution {
        phase: Phase,
        message: String,
    },
}

impl fmt::Display for NativePhaseError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Cancelled { phase } => write!(
                formatter,
                "native installer phase {phase:?} was cancelled before execution"
            ),
            Self::InvalidPlan { phase, operation } => write!(
                formatter,
                "native installer operation {operation} is unavailable for invalid phase {phase:?}"
            ),
            Self::Execution { phase, message } => {
                write!(
                    formatter,
                    "native installer phase {phase:?} failed: {message}"
                )
            }
        }
    }
}

/// A typed phase executor suitable for `JobSupervisor` in production.
///
/// The plans are built before a worker can start, so malformed requests fail
/// before any lifecycle state is claimed.  The account password hash is
/// consumed by plan construction and is not retained by this type.
pub(crate) struct NativePhaseExecutor {
    storage_plan: InstallerPlan,
    execution_plan: InstallerExecutionPlan,
    bootc_request: crate::installer_bootc::BootcInstallInput,
    account: Option<crate::installer_accounts::CreateUserInput>,
    manual_mounts: Option<crate::installer_manual::ManualMountsInput>,
    source_imgref: String,
    target_imgref: String,
    secure_boot_kernel: String,
    secure_boot_force_stage: bool,
    // L1: the MOK password is zeroized when the executor drops, so a crash
    // dump or a lingering process image cannot expose it after staging.
    secure_boot_password: zeroize::Zeroizing<String>,
    transaction_id: String,
    transaction_path: String,
    transaction: Mutex<crate::installer_transaction::TransactionState>,
    mounts: Mutex<crate::installer_mount::MountRegistry>,
    storage_target: Mutex<Option<String>>,
    secure_boot_state: Mutex<Option<String>>,
    /// H4: crash-recovery journal, opened before the first destructive
    /// mutation of the Storage phase.
    durable_journal: Mutex<Option<DurableJournal>>,
}

impl NativePhaseExecutor {
    pub(crate) fn from_request(request: NativeInstallRequest) -> Result<Self, String> {
        let bootc_request = request.execution.bootc.clone();
        let account = request.execution.account.clone();
        let manual_mounts = request.manual_mounts;
        let source_imgref = request.execution.bootc.source_imgref.clone();
        let target_imgref = request.execution.bootc.target_imgref.clone();
        let secure_boot_kernel = request.execution.secure_boot.kernel.clone();
        let secure_boot_force_stage = request.execution.secure_boot.force_stage;
        let secure_boot_password = zeroize::Zeroizing::new(request.secure_boot_password);
        let transaction_path = request.transaction_path;
        let mut storage_plan = installer_plan::build_plan(request.storage)?;
        // H2: record the pre-shrink NTFS size in the plan before any
        // destructive step, so a retried install can detect an
        // already-completed shrink instead of shrinking twice. Best-effort:
        // a probe failure leaves it empty and the retry guard falls back to
        // the durable journal plus a live re-probe.
        if storage_plan.mode == "resize_ntfs" {
            if let Some(partition) = storage_plan.resize_partition.clone() {
                storage_plan.pre_shrink_bytes =
                    probe_partition_size_bytes(&storage_plan.disk, &partition);
            }
        }
        let execution_plan = installer_executor::build_plan(request.execution)?;
        let transaction_id = Self::new_transaction_id();
        let transaction = Self::initial_transaction(
            &storage_plan,
            &source_imgref,
            &target_imgref,
            transaction_id.clone(),
        );
        Ok(Self {
            storage_plan,
            execution_plan,
            bootc_request,
            account,
            manual_mounts,
            source_imgref,
            target_imgref,
            secure_boot_kernel,
            secure_boot_force_stage,
            secure_boot_password,
            transaction_id: transaction_id.clone(),
            transaction_path,
            transaction: Mutex::new(transaction),
            mounts: Mutex::new(crate::installer_mount::MountRegistry::default()),
            storage_target: Mutex::new(None),
            secure_boot_state: Mutex::new(None),
            durable_journal: Mutex::new(None),
        })
    }

    pub(crate) fn from_plans(
        storage_plan: InstallerPlan,
        execution_plan: InstallerExecutionPlan,
    ) -> Self {
        let transaction_id = Self::new_transaction_id();
        let transaction = Self::initial_transaction(&storage_plan, "", "", transaction_id.clone());
        Self {
            storage_plan,
            execution_plan,
            bootc_request: crate::installer_bootc::BootcInstallInput {
                subcommand: "to-disk".to_string(),
                source_imgref: String::new(),
                target_imgref: String::new(),
                target: String::new(),
                skip_fetch_check: false,
                skip_finalize: false,
                root_subvolume: false,
                wipe: false,
                encryption: String::new(),
                tpm_recovery_ack: false,
            },
            account: None,
            manual_mounts: None,
            source_imgref: "".to_string(),
            target_imgref: "".to_string(),
            secure_boot_kernel: "fedora".to_string(),
            secure_boot_force_stage: false,
            secure_boot_password: zeroize::Zeroizing::new(String::new()),
            transaction_id: transaction_id.clone(),
            transaction_path: "/run/kyth-installer/txn/transaction.json".to_string(),
            transaction: Mutex::new(transaction),
            mounts: Mutex::new(crate::installer_mount::MountRegistry::default()),
            storage_target: Mutex::new(None),
            secure_boot_state: Mutex::new(None),
            durable_journal: Mutex::new(None),
        }
    }

    fn new_transaction_id() -> String {
        format!(
            "native-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|duration| duration.as_nanos())
                .unwrap_or_default()
        )
    }

    fn initial_transaction(
        storage_plan: &InstallerPlan,
        source_imgref: &str,
        target_imgref: &str,
        transaction_id: String,
    ) -> crate::installer_transaction::TransactionState {
        let source_kind = if source_imgref.starts_with("docker://") {
            "network"
        } else if source_imgref.starts_with("oci:") {
            "embedded"
        } else if source_imgref.is_empty() {
            "unresolved"
        } else {
            "local"
        };
        let source_status =
            crate::installer_readonly::source_status_for(source_imgref, target_imgref);
        let source = source_status
            .get("kind")
            .and_then(serde_json::Value::as_str)
            .unwrap_or(source_kind);
        let digest = source_status
            .get("digest")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        let verified = source_status
            .get("verified")
            .and_then(serde_json::Value::as_bool)
            .unwrap_or(false);
        crate::installer_transaction::TransactionState {
            schema_version: 1,
            transaction_id,
            job_id: None,
            updated_at: String::new(),
            status: String::new(),
            phase: "prepare".to_string(),
            lifecycle: "idle".to_string(),
            install_mode: storage_plan.mode.clone(),
            disk: storage_plan.disk.clone(),
            target_partition: storage_plan
                .target_partition
                .clone()
                .or_else(|| storage_plan.resize_partition.clone())
                .unwrap_or_default(),
            source: crate::installer_transaction::TransactionSource {
                kind: source.to_string(),
                digest: digest.to_string(),
                verified,
                target_ref: target_imgref.to_string(),
            },
            checks: Vec::new(),
            partition_steps: Vec::new(),
            message: String::new(),
            recovery_required: false,
        }
    }

    pub(crate) fn storage_plan(&self) -> &InstallerPlan {
        &self.storage_plan
    }

    /// Selection-time disk identity for M5: re-probe and fail closed if the
    /// disk at `storage_plan.disk` is not the disk the user selected.
    fn target_disk_identity(&self) -> crate::installer_storage::DiskIdentity {
        crate::installer_storage::DiskIdentity {
            serial: self.storage_plan.target_disk_serial.clone(),
            model: self.storage_plan.target_disk_model.clone(),
            size_bytes: self.storage_plan.target_disk_size_bytes,
        }
    }

    /// Validate the target disk including the selection-time identity (M5).
    fn validate_target_disk(&self, phase: Phase) -> Result<(), NativePhaseError> {
        crate::installer_guard::validate_target_disk_with_identity(
            &self.storage_plan.disk,
            &self.target_disk_identity(),
        )
        .map_err(|message| NativePhaseError::Execution { phase, message })
    }

    pub(crate) fn execution_plan(&self) -> &InstallerExecutionPlan {
        &self.execution_plan
    }

    /// Return the only operation sequence this adapter may expose to the
    /// native job.  The sequence is also useful for fixture-based parity tests
    /// before the corresponding live operation is implemented.
    pub(crate) fn operation_order(&self) -> Vec<NativeOperation> {
        let mut operations = vec![
            NativeOperation::ValidateStoragePlan,
            NativeOperation::ValidateExecutionPlan,
            NativeOperation::StorageMutation,
            NativeOperation::ImageWrite,
            NativeOperation::ConfigurationWrite,
        ];
        if self.execution_plan.account.is_some() {
            operations.push(NativeOperation::AccountCreate);
        }
        operations.extend([
            NativeOperation::SecureBootInteraction,
            NativeOperation::CompletionCommit,
        ]);
        operations
    }

    pub(crate) fn execute_phase_typed(
        &self,
        phase: Phase,
        cancellation: &CancellationToken,
    ) -> Result<(), NativePhaseError> {
        if cancellation.is_cancelled() {
            return Err(NativePhaseError::Cancelled { phase });
        }
        let start_status = match phase {
            Phase::Prepare => Some(("started", "Installer started")),
            Phase::Configure => Some(("configure_started", "Configuring the installed system")),
            _ => None,
        };
        if let Some((status, message)) = start_status {
            self.write_transaction(status, phase, "installing", message)
                .map_err(|message| NativePhaseError::Execution { phase, message })?;
        }

        let result = match phase {
            Phase::Prepare => {
                let power = crate::installer_orchestration::power_check();
                self.append_check(serde_json::json!({
                    "name": "power",
                    "status": power.status.clone(),
                    "detail": power.detail.clone()
                }))?;
                if power.status == "fail" {
                    Err(NativePhaseError::Execution {
                        phase,
                        message: power.detail.clone(),
                    })
                } else {
                    self.append_check(serde_json::json!({
                        "name": "native_plan",
                        "status": "pass",
                        "detail": "Typed Rust installer plan validated"
                    }))?;
                    Ok(())
                }
            }
            Phase::Storage => self.execute_storage(phase, cancellation),
            Phase::Image => self.execute_image(phase, cancellation),
            Phase::Configure => self.execute_configuration(phase, cancellation),
            Phase::SecureBoot => self.execute_secure_boot(phase, cancellation),
            Phase::Complete => self.execute_complete(phase),
        };
        result?;

        let completion = match phase {
            Phase::Prepare => Some(("prepared", "Install plan prepared")),
            // M13: the image phase writes the OS image; the old
            // "storage_complete" name misattributed it to the storage phase.
            Phase::Image => Some(("image_complete", "Operating system image written")),
            Phase::Configure => Some(("configure_complete", "Installed system configured")),
            Phase::SecureBoot => Some((
                "secure_boot_staged",
                "Secure Boot enrollment state classified",
            )),
            Phase::Complete => None,
            Phase::Storage => None,
        };
        if let Some((status, message)) = completion {
            self.write_transaction(status, phase, "installing", message)
                .map_err(|message| NativePhaseError::Execution { phase, message })?;
        }
        Ok(())
    }

    fn write_transaction(
        &self,
        status: &str,
        phase: Phase,
        lifecycle: &str,
        message: &str,
    ) -> Result<(), String> {
        let updated_at = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(|error| format!("could not determine transaction timestamp: {error}"))?
            .as_secs()
            .to_string();
        let state = {
            let mut state = self
                .transaction
                .lock()
                .map_err(|_| "native transaction state is unavailable".to_string())?;
            if status == "started" {
                state.checks.clear();
                state.partition_steps.clear();
            }
            state.updated_at = updated_at;
            state.status = status.to_string();
            state.phase = serde_json::to_value(phase)
                .ok()
                .and_then(|value| value.as_str().map(str::to_string))
                .unwrap_or_else(|| "unknown".to_string());
            state.lifecycle = lifecycle.to_string();
            state.message = message.to_string();
            state.recovery_required = status == "failed";
            state.clone()
        };
        crate::installer_transaction::write_request(
            crate::installer_transaction::TransactionWriteInput {
                path: self.transaction_path.clone(),
                state,
            },
        )
    }

    fn append_check(&self, check: serde_json::Value) -> Result<(), NativePhaseError> {
        self.append_check_for_phase(Phase::Prepare, check)
    }

    fn append_check_for_phase(
        &self,
        phase: Phase,
        check: serde_json::Value,
    ) -> Result<(), NativePhaseError> {
        let state = {
            let mut state = self
                .transaction
                .lock()
                .map_err(|_| NativePhaseError::Execution {
                    phase,
                    message: "native transaction state is unavailable".to_string(),
                })?;
            state.checks.push(check);
            state.clone()
        };
        crate::installer_transaction::write_request(
            crate::installer_transaction::TransactionWriteInput {
                path: self.transaction_path.clone(),
                state,
            },
        )
        .map_err(|message| NativePhaseError::Execution { phase, message })
    }

    fn append_partition_step(
        &self,
        kind: &str,
        status: &str,
        target: &str,
        phase: Phase,
    ) -> Result<(), NativePhaseError> {
        let state = {
            let mut state = self
                .transaction
                .lock()
                .map_err(|_| NativePhaseError::Execution {
                    phase,
                    message: "native transaction state is unavailable".to_string(),
                })?;
            let index = state.partition_steps.len();
            state.partition_steps.push(serde_json::json!({
                "index": index.to_string(),
                "kind": kind,
                "status": status,
                "target": target
            }));
            state.clone()
        };
        crate::installer_transaction::write_request(
            crate::installer_transaction::TransactionWriteInput {
                path: self.transaction_path.clone(),
                state,
            },
        )
        .map_err(|message| NativePhaseError::Execution { phase, message })
    }

    fn persist_failure_summary(&self, message: &str) {
        if let Ok(state) = self.transaction.lock().map(|state| state.clone()) {
            let path = std::env::var("KYTH_INSTALLER_FAILURE_SUMMARY")
                .unwrap_or_else(|_| "/run/kyth-installer/txn/failure.json".to_string());
            let _ = crate::installer_transaction::write_failure_summary(&path, &state, message);
        }
    }

    fn register_mount(&self, path: &str) -> Result<(), NativePhaseError> {
        self.mounts
            .lock()
            .map_err(|_| NativePhaseError::Execution {
                phase: Phase::Configure,
                message: "native mount state is unavailable".to_string(),
            })?
            .register(path);
        Ok(())
    }

    fn release_mount(&self, path: &str) -> Result<(), NativePhaseError> {
        self.mounts
            .lock()
            .map_err(|_| NativePhaseError::Execution {
                phase: Phase::Configure,
                message: "native mount state is unavailable".to_string(),
            })?
            .release(path);
        Ok(())
    }

    fn cleanup_mounts(&self, phase: Phase) -> Result<(), String> {
        let paths = self
            .mounts
            .lock()
            .map_err(|_| "native mount state is unavailable".to_string())?
            .cleanup_order();
        let cancellation = CancellationToken::default();
        let mut first_error = None;
        for path in paths {
            let operation = serde_json::json!({
                "operation": "unmount_filesystem",
                "mountpoint": path,
                "recursive": true,
                "lazy": true
            });
            if let Err(error) = self.execute_disk_helper(phase, &cancellation, &operation) {
                if first_error.is_none() {
                    first_error = Some(error.to_string());
                }
            }
        }
        first_error.map_or(Ok(()), Err)
    }

    fn execute_fixed_helper(
        &self,
        phase: Phase,
        cancellation: &CancellationToken,
        operation: &str,
        request: &serde_json::Value,
    ) -> Result<(), NativePhaseError> {
        let input = serde_json::to_vec(request).map_err(|error| NativePhaseError::Execution {
            phase,
            message: format!("could not encode {operation} request: {error}"),
        })?;
        let mut command = Command::new("/usr/bin/kyth-installer-exec");
        command.args(["--operation", operation]);
        let status = super::installer_stream::run_command_with_input(&mut command, &input, || {
            cancellation.is_cancelled()
        })
        .map_err(|message| NativePhaseError::Execution { phase, message })?;
        if status.success() {
            Ok(())
        } else {
            Err(NativePhaseError::Execution {
                phase,
                message: format!("{operation} helper exited with status {status}"),
            })
        }
    }

    fn execute_configuration(
        &self,
        phase: Phase,
        cancellation: &CancellationToken,
    ) -> Result<(), NativePhaseError> {
        let target = self
            .storage_target
            .lock()
            .map_err(|_| NativePhaseError::Execution {
                phase,
                message: "native storage target state is unavailable".to_string(),
            })?
            .clone();
        let config = &self.execution_plan.configuration;
        // config.target_root is the physical sysroot, which has no /etc of
        // its own; the installed system's /etc is inside the deployment the
        // image phase just wrote. Every /etc write below goes there.
        let deploy_root = installer_configuration::find_deploy_root(&config.target_root)
            .map_err(|message| NativePhaseError::Execution { phase, message })?;
        let deploy_fstab = format!("{deploy_root}/etc/fstab");
        let fstab = installer_configuration::snapshot_fstab(&deploy_fstab)
            .map_err(|message| NativePhaseError::Execution { phase, message })?;
        // H4: durable configure_started marker before the configure steps.
        self.record_journal(phase, "configure", OpState::Started)?;
        let result = (|| {
            match self.storage_plan.mode.as_str() {
                mode if lays_out_home_subvolume(mode) => {
                    let target_device = target
                        .or_else(|| self.storage_plan.target_partition.clone())
                        .ok_or_else(|| NativePhaseError::Execution {
                            phase,
                            message: "filesystem install has no configured target partition"
                                .to_string(),
                        })?;
                    self.execute_fixed_helper(
                        phase,
                        cancellation,
                        "alongside-home",
                        &serde_json::json!({
                            "config_root": config.target_root,
                            "target_device": target_device,
                            "fstab_path": deploy_fstab,
                        }),
                    )?;
                }
                "manual" => {
                    if let Some(mounts) = &self.manual_mounts {
                        // M4: hold the exclusive disk lock across the whole
                        // manual-mounts phase. Mounts mutate live block-device
                        // state and must not interleave with partitioning or
                        // a concurrent operator.
                        let _disk_lock =
                            crate::installer_guard::acquire_disk_lock(&self.storage_plan.disk)
                                .map_err(|message| NativePhaseError::Execution {
                                    phase,
                                    message,
                                })?;
                        let mut mounts = mounts.clone();
                        mounts.fstab_path = deploy_fstab.clone();
                        self.execute_fixed_helper(
                            phase,
                            cancellation,
                            "manual-mounts",
                            &serde_json::to_value(&mounts).map_err(|error| {
                                NativePhaseError::Execution {
                                    phase,
                                    message: format!("could not encode manual mounts: {error}"),
                                }
                            })?,
                        )?;
                    }
                }
                _ => {}
            }
            let deployed = config
                .for_deployment(&deploy_root)
                .map_err(|message| NativePhaseError::Execution { phase, message })?;
            installer_configuration::apply_plan(deployed)
                .map_err(|message| NativePhaseError::Execution { phase, message })?;
            if let Some(account) = &self.account {
                // useradd --root and the shadow edit need the deployment;
                // the home directory stays under the sysroot's shared /var.
                let mut account = account.clone();
                account.deploy_root = deploy_root.clone();
                let request = serde_json::to_value(&account).map_err(|error| {
                    NativePhaseError::Execution {
                        phase,
                        message: format!("could not encode create-user request: {error}"),
                    }
                })?;
                self.execute_fixed_helper(phase, cancellation, "create-user", &request)?;
            }
            let assurance =
                crate::installer_assurance::validate(crate::installer_assurance::AssuranceInput {
                    target_root: config.target_root.clone(),
                    deploy_root: deploy_root.clone(),
                    hostname: config
                        .writes
                        .iter()
                        .find(|write| write.path.ends_with("/hostname"))
                        .map(|write| write.content.trim().to_string())
                        .unwrap_or_default(),
                    locale: config
                        .writes
                        .iter()
                        .find(|write| write.path.ends_with("/locale.conf"))
                        .and_then(|write| write.content.strip_prefix("LANG="))
                        .map(str::trim)
                        .unwrap_or_default()
                        .to_string(),
                    keymap: config
                        .writes
                        .iter()
                        .find(|write| write.path.ends_with("/vconsole.conf"))
                        .and_then(|write| write.content.strip_prefix("KEYMAP="))
                        .map(str::trim)
                        .unwrap_or_default()
                        .to_string(),
                    timezone: config
                        .localtime_target
                        .strip_prefix("/usr/share/zoneinfo/")
                        .unwrap_or_default()
                        .to_string(),
                    username: self
                        .account
                        .as_ref()
                        .map(|account| account.username.clone())
                        .unwrap_or_default(),
                    // M8 (assurance side): the TPM keyslot check needs the
                    // requested encryption mode and the target disk.
                    encryption: self.bootc_request.encryption.clone(),
                    target_disk: self.storage_plan.disk.clone(),
                })
                .map_err(|message| NativePhaseError::Execution { phase, message })?;
            for check in assurance {
                self.append_check_for_phase(
                    phase,
                    serde_json::to_value(check).map_err(|error| NativePhaseError::Execution {
                        phase,
                        message: format!("could not encode assurance check: {error}"),
                    })?,
                )?;
            }
            Ok(())
        })();
        if let Err(error) = result {
            let rollback = installer_configuration::restore_fstab(fstab);
            if let Err(rollback_error) = rollback {
                return Err(NativePhaseError::Execution {
                    phase,
                    message: format!("{error}; fstab rollback failed: {rollback_error}"),
                });
            }
            return Err(error);
        }
        // H4: configure_complete marker after the configure steps succeed.
        self.record_journal(phase, "configure", OpState::Completed)?;
        Ok(())
    }

    fn write_terminal_transaction(&self, phase: Option<Phase>, message: &str) {
        let phase = phase.unwrap_or(Phase::Prepare);
        let _ = self.write_transaction("failed", phase, "failed", message);
    }

    fn verify_install_source(&self, phase: Phase) -> Result<(), NativePhaseError> {
        // Re-verify the image source immediately before bootc writes
        // anything. Key off the claimed source, not the reported kind: a
        // missing or tampered layout reports "invalid", which must also
        // refuse bootc.
        let source = self.source_imgref.trim();
        if source.starts_with("oci:") {
            // Re-verify the embedded image digest against the release digest
            // AND the build-time cosign signature bundle.
            // `source_status_for` fails closed on any mismatch.
            let status = crate::installer_readonly::source_status_for(
                &self.source_imgref,
                &self.target_imgref,
            );
            if !status
                .get("verified")
                .and_then(serde_json::Value::as_bool)
                .unwrap_or(false)
            {
                let detail = status
                    .get("message")
                    .and_then(serde_json::Value::as_str)
                    .unwrap_or("embedded image verification failed");
                return Err(NativePhaseError::Execution {
                    phase,
                    message: format!("refusing bootc install: {detail}"),
                });
            }
            return Ok(());
        }
        // M6: registry sources must be digest-pinned and cross-checked
        // against the ISO release metadata. Mirror
        // installer_readonly's normalization: an explicit docker://, or a
        // bare registry reference (which normalizes to docker://).
        // Other transports (containers-storage:, ostree:) keep deferring
        // to fetch-time checks.
        let explicit_transport = ["docker://", "containers-storage:", "oci:", "ostree:"]
            .iter()
            .any(|prefix| source.starts_with(prefix));
        let is_docker = source.starts_with("docker://") || !explicit_transport;
        if !is_docker {
            return Ok(());
        }
        self.verify_docker_source(phase, source)
    }

    /// M6: verify a `docker://` image source before bootc fetches it. The
    /// reference must be digest-pinned (`@sha256:`); the digest is then
    /// cross-checked against the `KYTH_SOURCE_DIGEST` environment pin, the
    /// ISO release metadata's `release_digest`, and the cosign signature
    /// bundle (`bundle.digest == digest` and
    /// `sha256(bundle) == metadata.signature_digest`). Anything else fails
    /// closed: a tag can be moved to different bytes after the ISO was
    /// built.
    fn verify_docker_source(&self, phase: Phase, source: &str) -> Result<(), NativePhaseError> {
        let refuse = |detail: String| NativePhaseError::Execution {
            phase,
            message: format!("refusing bootc install: {detail}"),
        };
        let digest = match source.rfind('@') {
            Some(at) => &source[at + 1..],
            None => {
                return Err(refuse(
                    "docker:// image source must be digest-pinned with @sha256:<digest>"
                        .to_string(),
                ));
            }
        };
        if !is_sha256_digest(digest) {
            return Err(refuse(
                "docker:// image source must be digest-pinned with @sha256:<64 hex digits>"
                    .to_string(),
            ));
        }
        // The ISO build pins its source digest in the environment; a missing
        // or mismatched pin fails closed.
        if std::env::var("KYTH_SOURCE_DIGEST")
            .unwrap_or_default()
            .trim()
            != digest
        {
            return Err(refuse(
                "docker:// image digest does not match the KYTH_SOURCE_DIGEST pinned by this ISO"
                    .to_string(),
            ));
        }
        let metadata_path = std::env::var("KYTH_SOURCE_METADATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("/usr/share/kyth/image-source.json"));
        let metadata = read_json_file(&metadata_path)
            .map_err(|error| refuse(format!("could not read image source metadata: {error}")))?;
        if metadata.get("schema_version").and_then(|v| v.as_u64()) != Some(1) {
            return Err(refuse(
                "image source metadata has an unsupported schema".to_string(),
            ));
        }
        if metadata.get("release_digest").and_then(|v| v.as_str()) != Some(digest) {
            return Err(refuse(
                "docker:// image digest does not match the release digest pinned by this ISO"
                    .to_string(),
            ));
        }
        let bundle_path = std::env::var("KYTH_SOURCE_SIGNATURE")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("/usr/share/kyth/image.sig.bundle.json"));
        let bundle_raw = read_regular_file(&bundle_path)
            .map_err(|error| refuse(format!("could not read image signature bundle: {error}")))?;
        let bundle: serde_json::Value = serde_json::from_slice(&bundle_raw)
            .map_err(|error| refuse(format!("image signature bundle is invalid: {error}")))?;
        if bundle.get("digest").and_then(|v| v.as_str()) != Some(digest) {
            return Err(refuse(
                "image signature bundle does not cover the pinned digest".to_string(),
            ));
        }
        let bundle_sha = sha256_file_hex(&bundle_path)
            .map_err(|error| refuse(format!("could not hash image signature bundle: {error}")))?;
        let expected_bundle_digest = format!("sha256:{bundle_sha}");
        if metadata.get("signature_digest").and_then(|v| v.as_str())
            != Some(expected_bundle_digest.as_str())
        {
            return Err(refuse(
                "image signature bundle does not match the digest pinned by this ISO release"
                    .to_string(),
            ));
        }
        Ok(())
    }

    fn check_storage_preflight(&self, phase: Phase) -> Result<(), NativePhaseError> {
        // H3: a tpm2 install without a TPM would encrypt a disk that can
        // never be unlocked. Probe TPM presence BEFORE any destructive
        // phase and fail closed when there is none.
        self.check_tpm_preflight(phase)?;
        // Live ESP-preservation / Windows / BitLocker preflight immediately
        // before mutation or bootc: locked BitLocker fails closed in every
        // mode, and non-wipe modes require an existing ESP to preserve.
        let sector_size = self.disk_sector_size(phase)?;
        let snapshot = self.disk_snapshot(phase, &self.storage_plan.disk)?;
        let preflight = crate::installer_storage::storage_preflight_from_snapshot(
            &snapshot,
            &self.storage_plan.disk,
            sector_size,
        )
        .map_err(|message| NativePhaseError::Execution { phase, message })?;
        crate::installer_storage::validate_storage_preflight(&preflight, &self.storage_plan.mode)
            .map_err(|message| NativePhaseError::Execution { phase, message })
    }

    /// H3: when TPM2 encryption was requested, refuse the install when no
    /// TPM is present. A TPM is present when `/dev/tpm0` exists or
    /// `tpm2_pcrread` exits 0; anything else fails closed with an actionable
    /// message before partitioning or bootc runs.
    fn check_tpm_preflight(&self, phase: Phase) -> Result<(), NativePhaseError> {
        if self.bootc_request.encryption.trim().to_ascii_lowercase() != "tpm2" {
            return Ok(());
        }
        let tpm_present = Path::new("/dev/tpm0").exists() || {
            ["/usr/bin/tpm2_pcrread", "/usr/sbin/tpm2_pcrread"]
                .iter()
                .any(|program| {
                    Command::new(program)
                        .stdout(std::process::Stdio::null())
                        .stderr(std::process::Stdio::null())
                        .status()
                        .map(|status| status.success())
                        .unwrap_or(false)
                })
        };
        if !tpm_present {
            return Err(NativePhaseError::Execution {
                phase,
                message: "TPM2 encryption was requested but no TPM was detected: /dev/tpm0 is missing and tpm2_pcrread failed. Refusing to install: without a TPM the encrypted disk could never be unlocked."
                    .to_string(),
            });
        }
        Ok(())
    }

    fn execute_image(
        &self,
        phase: Phase,
        cancellation: &CancellationToken,
    ) -> Result<(), NativePhaseError> {
        let _disk_lock = crate::installer_guard::acquire_disk_lock(&self.storage_plan.disk)
            .map_err(|message| NativePhaseError::Execution { phase, message })?;
        // L5: refuse the image phase when the target cannot hold the image
        // or available memory is too low to write it safely.
        self.check_image_resources(phase)?;
        self.verify_install_source(phase)?;
        self.check_storage_preflight(phase)?;
        if self.storage_plan.mode == "wipe" {
            self.validate_target_disk(phase)?;
        }
        // M13: durable image_started marker before bootc spawns.
        self.record_journal(phase, "image_write", OpState::Started)?;
        // M10: snapshot EFI boot entries before bootc can change them.
        let boot_entries_before = snapshot_boot_entries();
        let status = self.execute_stream_helper(
            phase,
            cancellation,
            serde_json::json!({
                "kind": "bootc_install",
                "request": self.bootc_request.clone(),
            }),
            None,
        )?;
        if status {
            // M10: warn if bootc deleted any named boot entry.
            self.warn_if_boot_entries_lost(phase, boot_entries_before)?;
            // M13: image_complete marker after a successful write.
            self.record_journal(phase, "image_write", OpState::Completed)?;
            if self.storage_plan.mode == "wipe" {
                self.mount_wipe_root(phase, cancellation)?;
            }
            Ok(())
        } else {
            Err(NativePhaseError::Execution {
                phase,
                message: format!("bootc exited with status {}", status),
            })
        }
    }

    fn execute_disk_helper(
        &self,
        phase: Phase,
        cancellation: &CancellationToken,
        operation: &serde_json::Value,
    ) -> Result<(), NativePhaseError> {
        let step_kind = operation
            .get("operation")
            .and_then(serde_json::Value::as_str)
            .filter(|kind| {
                matches!(
                    *kind,
                    "create_label"
                        | "create_partition"
                        | "create_unformatted_partition"
                        | "delete_partition"
                        | "resize_partition"
                        | "format_filesystem"
                        | "set_partition_flag"
                        | "filesystem_resize"
                        | "btrfs_subvolume_create"
                        | "btrfs_subvolume_set_default"
                )
            });
        let step_target = operation
            .get("partition")
            .or_else(|| operation.get("device"))
            .or_else(|| operation.get("disk"))
            .or_else(|| operation.get("mountpoint"))
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        if let Some(kind) = step_kind {
            self.append_partition_step(kind, "started", step_target, phase)?;
        }
        let input = serde_json::to_vec(operation).map_err(|error| NativePhaseError::Execution {
            phase,
            message: format!("could not encode disk operation: {error}"),
        })?;
        let mut command = Command::new("/usr/bin/kyth-installer-exec");
        command.args(["--operation", "disk"]);
        let status = super::installer_stream::run_command_with_input(&mut command, &input, || {
            cancellation.is_cancelled()
        })
        .map_err(|message| NativePhaseError::Execution { phase, message })?;
        if status.success() {
            if let Some(kind) = step_kind {
                self.append_partition_step(kind, "completed", step_target, phase)?;
            }
            Ok(())
        } else {
            if let Some(kind) = step_kind {
                let _ = self.append_partition_step(kind, "failed", step_target, phase);
            }
            Err(NativePhaseError::Execution {
                phase,
                message: format!("disk helper exited with status {status}"),
            })
        }
    }

    fn mount_wipe_root(
        &self,
        phase: Phase,
        cancellation: &CancellationToken,
    ) -> Result<(), NativePhaseError> {
        // M12: the image phase should have left the LUKS device open. A
        // closed mapper would surface below as the misleading "no Btrfs root
        // partition" error; fail with an actionable message instead.
        if self.bootc_request.encryption.trim().to_ascii_lowercase() == "tpm2"
            && !self.luks_mapper_open(phase)?
        {
            return Err(NativePhaseError::Execution {
                phase,
                message: "LUKS device closed after image write; cannot continue configure phase"
                    .to_string(),
            });
        }
        let output = Command::new("/usr/bin/lsblk")
            .args([
                "--json",
                "--bytes",
                "--paths",
                "--output",
                "NAME,TYPE,FSTYPE,PKNAME",
                &self.storage_plan.disk,
            ])
            .output()
            .map_err(|error| NativePhaseError::Execution {
                phase,
                message: format!("could not probe installed root partition: {error}"),
            })?;
        if !output.status.success() {
            return Err(NativePhaseError::Execution {
                phase,
                message: "installed root partition probe failed".to_string(),
            });
        }
        let snapshot =
            String::from_utf8(output.stdout).map_err(|_| NativePhaseError::Execution {
                phase,
                message: "installed root partition probe was not UTF-8".to_string(),
            })?;
        let root = crate::installer_storage::root_partition_from_snapshot(
            &snapshot,
            &self.storage_plan.disk,
        )
        .map_err(|message| NativePhaseError::Execution { phase, message })?;
        for operation in [
            serde_json::json!({
                "operation": "ensure_directory",
                "path": WIPE_STAGING_MOUNTPOINT
            }),
            serde_json::json!({
                "operation": "mount_filesystem",
                "device": root,
                "mountpoint": WIPE_STAGING_MOUNTPOINT
            }),
        ] {
            self.execute_disk_helper(phase, cancellation, &operation)?;
        }
        self.register_mount(WIPE_STAGING_MOUNTPOINT)?;
        Ok(())
    }

    fn disk_snapshot(&self, phase: Phase, disk: &str) -> Result<String, NativePhaseError> {
        let output = Command::new("/usr/bin/lsblk")
            .args([
                "--json",
                "--bytes",
                "--paths",
                "--output",
                "NAME,SIZE,TYPE,FSTYPE,PARTTYPE,PARTN,LABEL,MOUNTPOINT,MOUNTPOINTS,START,RO,PKNAME,PTTYPE",
                disk,
            ])
            .output()
            .map_err(|error| NativePhaseError::Execution {
                phase,
                message: format!("could not probe target disk: {error}"),
            })?;
        if !output.status.success() {
            return Err(NativePhaseError::Execution {
                phase,
                message: "target disk probe failed".to_string(),
            });
        }
        String::from_utf8(output.stdout).map_err(|_| NativePhaseError::Execution {
            phase,
            message: "target disk probe was not UTF-8".to_string(),
        })
    }

    /// H1: the target disk's real sector size from `blockdev --getss`,
    /// validated. The executor used to hardcode 512, which misaligns every
    /// partition-geometry check on 4Kn disks.
    fn disk_sector_size(&self, phase: Phase) -> Result<u64, NativePhaseError> {
        let output = Command::new("/usr/sbin/blockdev")
            .args(["--getss", &self.storage_plan.disk])
            .output()
            .map_err(|error| NativePhaseError::Execution {
                phase,
                message: format!("could not probe disk sector size: {error}"),
            })?;
        if !output.status.success() {
            return Err(NativePhaseError::Execution {
                phase,
                message: "disk sector-size probe failed".to_string(),
            });
        }
        let size: u64 = String::from_utf8(output.stdout)
            .map_err(|_| NativePhaseError::Execution {
                phase,
                message: "disk sector-size probe was not UTF-8".to_string(),
            })?
            .trim()
            .parse()
            .map_err(|_| NativePhaseError::Execution {
                phase,
                message: "disk sector-size probe returned an invalid size".to_string(),
            })?;
        // Only real-world sector sizes are accepted (mirroring the storage
        // layer's `valid_sector_size`); anything else fails closed instead
        // of feeding a bogus alignment into partition geometry.
        if !size.is_power_of_two() || !(512..=4096).contains(&size) {
            return Err(NativePhaseError::Execution {
                phase,
                message: format!("disk reports an unsupported sector size: {size}"),
            });
        }
        Ok(size)
    }

    /// H4: open the durable crash-recovery journal before the first
    /// destructive mutation. The journal lives on the ESP when the live
    /// session already has it mounted (so it survives a reboot), otherwise
    /// under the staging target root.
    fn open_durable_journal(&self, phase: Phase) -> Result<(), NativePhaseError> {
        let staging = Path::new(if self.storage_plan.mode == "wipe" {
            WIPE_STAGING_MOUNTPOINT
        } else {
            FILESYSTEM_STAGING_MOUNTPOINT
        });
        // Best-effort: a probe failure here must not block the install; the
        // staging fallback is always available.
        let esp_mount: Option<PathBuf> = (|| {
            let sector_size = self.disk_sector_size(phase).ok()?;
            let snapshot = self.disk_snapshot(phase, &self.storage_plan.disk).ok()?;
            let efi = crate::installer_storage::efi_partition_from_snapshot(
                &snapshot,
                &self.storage_plan.disk,
                sector_size,
            )
            .ok()??;
            efi.mounted_at.map(PathBuf::from)
        })();
        let journal = DurableJournal::open(esp_mount.as_deref(), staging)
            .map_err(|message| NativePhaseError::Execution { phase, message })?;
        *self
            .durable_journal
            .lock()
            .map_err(|_| NativePhaseError::Execution {
                phase,
                message: "native durable journal state is unavailable".to_string(),
            })? = Some(journal);
        Ok(())
    }

    /// H4: record a durable journal transition, fsync'd before returning. A
    /// journal failure fails the phase: without the marker a retry cannot
    /// know what already happened.
    fn record_journal(
        &self,
        phase: Phase,
        op: &str,
        state: OpState,
    ) -> Result<(), NativePhaseError> {
        let journal = self
            .durable_journal
            .lock()
            .map_err(|_| NativePhaseError::Execution {
                phase,
                message: "native durable journal state is unavailable".to_string(),
            })?;
        let journal = journal
            .as_ref()
            .ok_or_else(|| NativePhaseError::Execution {
                phase,
                message: "durable journal was not opened before the storage phase".to_string(),
            })?;
        journal
            .record(op, state)
            .map_err(|message| NativePhaseError::Execution { phase, message })
    }

    /// H4: true when the durable journal records `op` as completed. A missing
    /// journal counts as "not completed"; an unreadable one fails closed.
    fn journal_completed(&self, phase: Phase, op: &str) -> Result<bool, NativePhaseError> {
        let journal = self
            .durable_journal
            .lock()
            .map_err(|_| NativePhaseError::Execution {
                phase,
                message: "native durable journal state is unavailable".to_string(),
            })?;
        let Some(journal) = journal.as_ref() else {
            return Ok(false);
        };
        DurableJournal::load(journal.path())
            .map(|state| state.completed(op))
            .map_err(|message| NativePhaseError::Execution { phase, message })
    }

    /// H2: make sure the durable journal is on the ESP before the
    /// destructive NTFS shrink, so a reboot between the shrink and the end
    /// of the install cannot lose the completion record. Mounts the target
    /// ESP at a scratch mountpoint when the live session has not already
    /// mounted it.
    fn ensure_esp_journal(
        &self,
        phase: Phase,
        cancellation: &CancellationToken,
    ) -> Result<(), NativePhaseError> {
        const ESP_SCRATCH_MOUNTPOINT: &str = "/run/kyth-installer/esp-journal";
        let sector_size = self.disk_sector_size(phase)?;
        let snapshot = self.disk_snapshot(phase, &self.storage_plan.disk)?;
        let efi = crate::installer_storage::efi_partition_from_snapshot(
            &snapshot,
            &self.storage_plan.disk,
            sector_size,
        )
        .map_err(|message| NativePhaseError::Execution { phase, message })?
        .ok_or_else(|| NativePhaseError::Execution {
            phase,
            message: "no EFI system partition found; cannot place the durable install journal"
                .to_string(),
        })?;
        let mountpoint: String = match efi.mounted_at {
            Some(mounted_at) => mounted_at,
            None => {
                for operation in [
                    serde_json::json!({
                        "operation": "ensure_directory",
                        "path": ESP_SCRATCH_MOUNTPOINT
                    }),
                    serde_json::json!({
                        "operation": "mount_filesystem",
                        "device": efi.name,
                        "mountpoint": ESP_SCRATCH_MOUNTPOINT
                    }),
                ] {
                    self.execute_disk_helper(phase, cancellation, &operation)?;
                }
                self.register_mount(ESP_SCRATCH_MOUNTPOINT)?;
                ESP_SCRATCH_MOUNTPOINT.to_string()
            }
        };
        let dest = Path::new(&mountpoint).join(JOURNAL_FILE_NAME);
        let relocated = {
            let journal = self
                .durable_journal
                .lock()
                .map_err(|_| NativePhaseError::Execution {
                    phase,
                    message: "native durable journal state is unavailable".to_string(),
                })?;
            match journal.as_ref() {
                Some(journal) if journal.path() == dest.as_path() => return Ok(()),
                Some(journal) => journal
                    .relocate(&dest)
                    .map_err(|message| NativePhaseError::Execution { phase, message })?,
                None => {
                    return Err(NativePhaseError::Execution {
                        phase,
                        message: "durable journal was not opened before the storage phase"
                            .to_string(),
                    });
                }
            }
        };
        *self
            .durable_journal
            .lock()
            .map_err(|_| NativePhaseError::Execution {
                phase,
                message: "native durable journal state is unavailable".to_string(),
            })? = Some(relocated);
        Ok(())
    }

    /// L5: disk-space and memory preflight before the image phase. Fails
    /// closed when the target cannot hold the image (ENOSPC risk) or
    /// available memory is too low to write it safely (OOM risk).
    fn check_image_resources(&self, phase: Phase) -> Result<(), NativePhaseError> {
        let fail = |message: String| NativePhaseError::Execution { phase, message };
        let image_bytes = self.estimate_image_bytes();
        if self.storage_plan.mode == "wipe" {
            // The staging mountpoint is not mounted yet in wipe mode, so
            // check the whole disk instead of statvfs on the live /run.
            let disk_bytes = probe_disk_size_bytes(&self.storage_plan.disk).ok_or_else(|| {
                fail("could not determine target disk size before the image phase".to_string())
            })?;
            if disk_bytes < image_bytes {
                return Err(fail(format!(
                    "target disk is too small for the install image: disk holds {disk_bytes} bytes, image needs ~{image_bytes} bytes"
                )));
            }
        } else {
            let available =
                statvfs_available_bytes(FILESYSTEM_STAGING_MOUNTPOINT).ok_or_else(|| {
                    fail("could not determine free space on the install target".to_string())
                })?;
            if available < image_bytes {
                return Err(fail(format!(
                    "not enough free space for the install image: {available} bytes available, ~{image_bytes} bytes needed"
                )));
            }
        }
        const MIN_MEM_AVAILABLE_BYTES: u64 = 2 * 1024 * 1024 * 1024;
        let mem_available = mem_available_bytes().ok_or_else(|| {
            fail("could not read available memory before the image phase".to_string())
        })?;
        if mem_available < MIN_MEM_AVAILABLE_BYTES {
            return Err(fail(format!(
                "not enough available memory to safely write the install image: {mem_available} bytes available, {MIN_MEM_AVAILABLE_BYTES} bytes required"
            )));
        }
        Ok(())
    }

    /// L5: image size estimate for the resource preflight. The embedded OCI
    /// layout is measured exactly from its manifest; otherwise an
    /// environment override wins, falling back to a documented estimate
    /// (~8.5 GiB compressed per installer/build.sh, plus extraction
    /// headroom).
    fn estimate_image_bytes(&self) -> u64 {
        const ESTIMATED_IMAGE_BYTES: u64 = 10 * 1024 * 1024 * 1024;
        if let Ok(value) = std::env::var("KYTH_IMAGE_BYTES") {
            if let Ok(bytes) = value.trim().parse::<u64>() {
                if bytes > 0 {
                    return bytes;
                }
            }
        }
        let source = self.source_imgref.trim();
        if source.starts_with("oci:") {
            if let Some(bytes) = oci_layout_bytes(source) {
                return bytes;
            }
        }
        ESTIMATED_IMAGE_BYTES
    }

    /// M10: compare the post-bootc EFI boot entries against the pre-bootc
    /// snapshot and emit a warning check when any named entry disappeared.
    /// Best-effort: a missing snapshot (e.g. BIOS boot, no efibootmgr) skips
    /// the comparison silently.
    fn warn_if_boot_entries_lost(
        &self,
        phase: Phase,
        before: Option<Vec<(String, String)>>,
    ) -> Result<(), NativePhaseError> {
        let Some(before) = before else {
            return Ok(());
        };
        if before.is_empty() {
            return Ok(());
        }
        let Some(after) = snapshot_boot_entries() else {
            return Ok(());
        };
        let after_numbers: HashSet<&str> =
            after.iter().map(|(number, _)| number.as_str()).collect();
        let lost: Vec<String> = before
            .iter()
            .filter(|(number, _)| !after_numbers.contains(number.as_str()))
            .map(|(number, label)| {
                if label.is_empty() {
                    format!("Boot{number}")
                } else {
                    format!("Boot{number} ({label})")
                }
            })
            .collect();
        if !lost.is_empty() {
            self.append_check_for_phase(
                phase,
                serde_json::json!({
                    "name": "boot_entries",
                    "status": "warning",
                    "detail": format!(
                        "EFI boot entries disappeared during the image write: {}. The installed system should still boot, but previously installed operating systems may no longer appear in the firmware boot menu.",
                        lost.join(", ")
                    ),
                }),
            )?;
        }
        Ok(())
    }

    /// M12: true when a device-mapper crypt device exists under the target
    /// disk, i.e. the LUKS device bootc opened is still open. Name-agnostic:
    /// it detects any `TYPE == "crypt"` descendant rather than guessing
    /// bootc's mapper name.
    fn luks_mapper_open(&self, phase: Phase) -> Result<bool, NativePhaseError> {
        let output = Command::new("/usr/bin/lsblk")
            .args([
                "--json",
                "--bytes",
                "--paths",
                "--output",
                "NAME,TYPE",
                &self.storage_plan.disk,
            ])
            .output()
            .map_err(|error| NativePhaseError::Execution {
                phase,
                message: format!("could not probe LUKS mapper state: {error}"),
            })?;
        if !output.status.success() {
            return Err(NativePhaseError::Execution {
                phase,
                message: "LUKS mapper state probe failed".to_string(),
            });
        }
        let snapshot: serde_json::Value =
            serde_json::from_slice(&output.stdout).map_err(|_| NativePhaseError::Execution {
                phase,
                message: "LUKS mapper state probe was not valid JSON".to_string(),
            })?;
        fn has_crypt(device: &serde_json::Value) -> bool {
            if device.get("type").and_then(|v| v.as_str()) == Some("crypt") {
                return true;
            }
            device
                .get("children")
                .and_then(|v| v.as_array())
                .is_some_and(|children| children.iter().any(has_crypt))
        }
        Ok(snapshot
            .get("blockdevices")
            .and_then(|v| v.as_array())
            .is_some_and(|devices| devices.iter().any(has_crypt)))
    }

    fn execute_stream_helper(
        &self,
        phase: Phase,
        cancellation: &CancellationToken,
        operation: serde_json::Value,
        partition_step: Option<(&str, &str)>,
    ) -> Result<bool, NativePhaseError> {
        let step_kind = operation
            .get("request")
            .and_then(|request| request.get("operation"))
            .and_then(serde_json::Value::as_str)
            .filter(|kind| *kind == "filesystem_resize")
            .or_else(|| partition_step.map(|(kind, _)| kind));
        let step_target = operation
            .get("request")
            .and_then(|request| request.get("device"))
            .and_then(serde_json::Value::as_str)
            .or_else(|| partition_step.map(|(_, target)| target))
            .unwrap_or_default();
        if let Some(kind) = step_kind {
            self.append_partition_step(kind, "started", step_target, phase)?;
        }
        let input =
            serde_json::to_vec(&operation).map_err(|error| NativePhaseError::Execution {
                phase,
                message: format!("could not encode streaming disk operation: {error}"),
            })?;
        let mut command = Command::new("/usr/bin/kyth-installer-exec");
        command.args(["--operation", "stream"]);
        let status = super::installer_stream::run_command_with_input(&mut command, &input, || {
            cancellation.is_cancelled()
        })
        .map_err(|message| NativePhaseError::Execution { phase, message })?;
        if status.success() {
            if let Some(kind) = step_kind {
                self.append_partition_step(kind, "completed", step_target, phase)?;
            }
            Ok(true)
        } else {
            if let Some(kind) = step_kind {
                let _ = self.append_partition_step(kind, "failed", step_target, phase);
            }
            Err(NativePhaseError::Execution {
                phase,
                message: format!("streaming disk helper exited with status {status}"),
            })
        }
    }

    /// Pure control-flow core of [`Self::guarded_table_mutation`]: run `body`,
    /// and on failure invoke `restore` before propagating the original error.
    /// A restore failure never replaces or masks the mutation's own error —
    /// callers learn what actually broke the disk operation.
    fn run_guarded<T, E>(
        body: impl FnOnce() -> Result<T, E>,
        restore: impl FnOnce() -> Result<(), E>,
    ) -> Result<T, (E, Option<E>)> {
        match body() {
            Ok(value) => Ok(value),
            Err(error) => Err((error, restore().err())),
        }
    }

    /// Back up `disk`'s partition table, run `body`, and restore the table if
    /// `body` fails. Mirrors Python's `PartitionTableGuard`
    /// (`storage_guard.py`), which both the manual Journal commit
    /// (`installer_journal.rs`'s `commit_request`, already ported) and this
    /// guided-install partition creation share in the Python original —
    /// `commit_new_kythos_partition` always wraps bios-boot creation, the
    /// new KythOS partition, and (for a resize-NTFS install) the preceding
    /// `resizepart` boundary move in one backed-up/restored scope. Restore
    /// runs on a fresh, never-cancelled token (like `cleanup_mounts`): a
    /// cancellation that triggered `body`'s failure must not also block the
    /// table restore.
    fn guarded_table_mutation<T>(
        &self,
        phase: Phase,
        body: impl FnOnce() -> Result<T, NativePhaseError>,
    ) -> Result<T, NativePhaseError> {
        let _disk_lock = crate::installer_guard::acquire_disk_lock(&self.storage_plan.disk)
            .map_err(|message| NativePhaseError::Execution { phase, message })?;
        self.validate_target_disk(phase)?;
        let directory = tempfile::Builder::new()
            .prefix("kyth-partition-")
            .tempdir()
            .map_err(|error| NativePhaseError::Execution {
                phase,
                message: format!("could not create partition backup directory: {error}"),
            })?;
        let backup_path = directory
            .path()
            .join("partition-table.backup")
            .to_string_lossy()
            .into_owned();
        let backup_cancellation = CancellationToken::default();
        self.execute_disk_helper(
            phase,
            &backup_cancellation,
            &serde_json::json!({
                "operation": "backup_table",
                "disk": &self.storage_plan.disk,
                "backup_path": backup_path,
            }),
        )?;
        match Self::run_guarded(body, || {
            let restore_cancellation = CancellationToken::default();
            self.execute_disk_helper(
                phase,
                &restore_cancellation,
                &serde_json::json!({
                    "operation": "restore_table",
                    "disk": &self.storage_plan.disk,
                    "backup_path": backup_path,
                }),
            )
        }) {
            Ok(value) => Ok(value),
            Err((operation_error, None)) => Err(operation_error),
            Err((operation_error, Some(restore_error))) => Err(NativePhaseError::Execution {
                phase,
                message: format!(
                    "{operation_error}; partition-table restore also failed: {restore_error}"
                ),
            }),
        }
    }

    fn create_target_partition(
        &self,
        phase: Phase,
        cancellation: &CancellationToken,
        start: u64,
        end: u64,
        // H1: the real sector size from `blockdev --getss`, threaded through
        // instead of a hardcoded 512 that misaligns every geometry check on
        // 4Kn disks.
        sector_size: u64,
    ) -> Result<String, NativePhaseError> {
        const BIOS_BOOT_BYTES: u64 = 1024 * 1024;
        if end <= start {
            return Err(NativePhaseError::Execution {
                phase,
                message: "free-space target has invalid geometry".to_string(),
            });
        }
        let mut before = self.disk_snapshot(phase, &self.storage_plan.disk)?;
        let mut target_start = start;
        if !crate::installer_storage::has_bios_boot_partition(&before, sector_size)
            .map_err(|message| NativePhaseError::Execution { phase, message })?
        {
            if end - start < BIOS_BOOT_BYTES + sector_size {
                return Err(NativePhaseError::Execution {
                    phase,
                    message: "free-space target cannot fit a BIOS boot partition".to_string(),
                });
            }
            self.execute_disk_helper(
                phase,
                cancellation,
                &serde_json::json!({
                    "operation": "create_unformatted_partition",
                    "disk": &self.storage_plan.disk,
                    "start": start,
                    "size": BIOS_BOOT_BYTES,
                    "label": "biosboot",
                    "sector_size": sector_size
                }),
            )?;
            let after = self.disk_snapshot(phase, &self.storage_plan.disk)?;
            let bios = crate::installer_storage::new_partition_from_snapshots(
                &before,
                &after,
                start,
                BIOS_BOOT_BYTES,
                sector_size,
            )
            .map_err(|message| NativePhaseError::Execution { phase, message })?;
            let bios_probe = crate::installer_storage::partition_probe_from_snapshot(
                &after,
                &self.storage_plan.disk,
                &bios,
                sector_size,
            )
            .map_err(|message| NativePhaseError::Execution { phase, message })?;
            self.execute_disk_helper(
                phase,
                cancellation,
                &serde_json::json!({
                    "operation": "set_partition_flag",
                    "disk": &self.storage_plan.disk,
                    "part_num": bios_probe.number,
                    "flag": "bios_grub",
                    "enabled": true
                }),
            )?;
            before = after;
            target_start = target_start.saturating_add(BIOS_BOOT_BYTES);
        }
        let target_size =
            end.checked_sub(target_start)
                .ok_or_else(|| NativePhaseError::Execution {
                    phase,
                    message: "free-space target has invalid post-boot geometry".to_string(),
                })?;
        if target_size < 32 * 1024 * 1024 * 1024 {
            return Err(NativePhaseError::Execution {
                phase,
                message: "free-space target is smaller than the KythOS minimum".to_string(),
            });
        }
        self.execute_disk_helper(
            phase,
            cancellation,
            &serde_json::json!({
                "operation": "create_partition",
                "disk": &self.storage_plan.disk,
                "start": target_start,
                "size": target_size,
                "fs": "btrfs",
                "label": "KythOS",
                "sector_size": sector_size
            }),
        )?;
        let after = self.disk_snapshot(phase, &self.storage_plan.disk)?;
        let target = crate::installer_storage::new_partition_from_snapshots(
            &before,
            &after,
            target_start,
            target_size,
            sector_size,
        )
        .map_err(|message| NativePhaseError::Execution { phase, message })?;
        crate::installer_storage::partition_probe_from_snapshot(
            &after,
            &self.storage_plan.disk,
            &target,
            sector_size,
        )
        .map_err(|message| NativePhaseError::Execution { phase, message })?;
        Ok(target)
    }

    fn resize_ntfs_target(
        &self,
        phase: Phase,
        cancellation: &CancellationToken,
    ) -> Result<String, NativePhaseError> {
        const MIN_WINDOWS_BYTES: u64 = 64 * 1024 * 1024 * 1024;
        if !super::installer_daemon::ac_online_in(std::path::Path::new("/sys/class/power_supply")) {
            return Err(NativePhaseError::Execution {
                phase,
                message: "Connect AC power before shrinking Windows. Power loss during a filesystem or partition resize can leave the disk unbootable.".to_string(),
            });
        }
        let partition = self
            .storage_plan
            .resize_partition
            .as_deref()
            .ok_or_else(|| NativePhaseError::Execution {
                phase,
                message: "NTFS resize has no selected partition".to_string(),
            })?;
        // H1: the real sector size, validated, instead of a hardcoded 512.
        let sector_size = self.disk_sector_size(phase)?;
        let before = self.disk_snapshot(phase, &self.storage_plan.disk)?;
        let probe = crate::installer_storage::partition_probe_from_snapshot(
            &before,
            &self.storage_plan.disk,
            partition,
            sector_size,
        )
        .map_err(|message| NativePhaseError::Execution { phase, message })?;
        if !matches!(probe.fstype.as_str(), "ntfs" | "ntfs3") {
            return Err(NativePhaseError::Execution {
                phase,
                message: "Only NTFS partitions can be resized by this installer path".to_string(),
            });
        }
        if probe.efi || probe.current || probe.in_use || probe.read_only {
            return Err(NativePhaseError::Execution {
                phase,
                message: "The selected NTFS partition is mounted, read-only, or reserved"
                    .to_string(),
            });
        }
        // H2: crash+retry guard. A previous run that completed the shrink
        // recorded `ntfs_shrink` in the durable journal; shrinking again
        // would double-shrink Windows. When the partition is already at or
        // past the target size and the freed region is still free and large
        // enough, skip the destructive resize and continue to partitioning.
        // (The pre-shrink size itself was recorded in the plan at request
        // time, before any destructive step.)
        if let Some((new_end, old_end)) =
            self.ntfs_shrink_resume_window(phase, &before, &probe, sector_size)?
        {
            return self.create_target_partition(
                phase,
                cancellation,
                new_end,
                old_end,
                sector_size,
            );
        }
        // H2: the shrink's completion record must survive a reboot, so the
        // journal moves onto the ESP before the destructive resize.
        self.ensure_esp_journal(phase, cancellation)?;
        let new_size = probe
            .size_bytes
            .checked_sub(self.storage_plan.resize_bytes)
            .ok_or_else(|| NativePhaseError::Execution {
                phase,
                message: "NTFS shrink exceeds the selected partition size".to_string(),
            })?;
        if new_size < MIN_WINDOWS_BYTES || new_size % sector_size != 0 {
            return Err(NativePhaseError::Execution {
                phase,
                message: "NTFS shrink would leave an unsafe or unaligned Windows partition"
                    .to_string(),
            });
        }
        self.record_journal(phase, "ntfs_shrink", OpState::Started)?;
        for stage in ["check", "info", "dry_run", "resize"] {
            self.execute_stream_helper(
                phase,
                cancellation,
                serde_json::json!({
                    "kind": "disk",
                    "request": {
                        "operation": "filesystem_resize",
                        "device": partition,
                        "fs": "ntfs",
                        "new_size_bytes": new_size,
                        "stage": stage
                    }
                }),
                Some(("filesystem_resize", partition)),
            )?;
        }
        // L4: re-resolve the partition number from a fresh snapshot
        // immediately before moving the boundary. `probe.number` came from a
        // pre-shrink snapshot; a concurrent table change could have
        // renumbered the partition, and resizing the wrong number would
        // destroy a different partition.
        let fresh = self.disk_snapshot(phase, &self.storage_plan.disk)?;
        let fresh_probe = crate::installer_storage::partition_probe_from_snapshot(
            &fresh,
            &self.storage_plan.disk,
            partition,
            sector_size,
        )
        .map_err(|message| NativePhaseError::Execution { phase, message })?;
        if fresh_probe.start_bytes != probe.start_bytes
            || fresh_probe.size_bytes.abs_diff(probe.size_bytes) > sector_size
        {
            return Err(NativePhaseError::Execution {
                phase,
                message: "NTFS partition changed during the filesystem shrink; refusing to move its boundary"
                    .to_string(),
            });
        }
        self.execute_disk_helper(
            phase,
            cancellation,
            &serde_json::json!({
                "operation": "resize_partition",
                "disk": &self.storage_plan.disk,
                "part_num": fresh_probe.number,
                "start": fresh_probe.start_bytes,
                "new_size": new_size,
                "sector_size": sector_size
            }),
        )?;
        let after = self.disk_snapshot(phase, &self.storage_plan.disk)?;
        let resized = crate::installer_storage::partition_probe_from_snapshot(
            &after,
            &self.storage_plan.disk,
            partition,
            sector_size,
        )
        .map_err(|message| NativePhaseError::Execution { phase, message })?;
        if resized.size_bytes.abs_diff(new_size) > sector_size {
            return Err(NativePhaseError::Execution {
                phase,
                message: "NTFS partition boundary did not match the requested size".to_string(),
            });
        }
        self.record_journal(phase, "ntfs_shrink", OpState::Completed)?;
        let old_end = probe
            .start_bytes
            .checked_add(probe.size_bytes)
            .ok_or_else(|| NativePhaseError::Execution {
                phase,
                message: "NTFS partition geometry overflowed".to_string(),
            })?;
        let new_end =
            probe
                .start_bytes
                .checked_add(new_size)
                .ok_or_else(|| NativePhaseError::Execution {
                    phase,
                    message: "NTFS target geometry overflowed".to_string(),
                })?;
        self.create_target_partition(phase, cancellation, new_end, old_end, sector_size)
    }

    /// H2 crash-retry guard for the guided NTFS shrink. Returns the
    /// `(new_end, old_end)` window for `create_target_partition` when a
    /// previous run already shrank the partition and the freed space is
    /// still intact; returns `None` when the shrink still has to run. The
    /// durable journal is the completion signal: only a recorded
    /// `ntfs_shrink` completion can skip the destructive resize.
    fn ntfs_shrink_resume_window(
        &self,
        phase: Phase,
        snapshot: &str,
        probe: &crate::installer_storage::PartitionProbe,
        sector_size: u64,
    ) -> Result<Option<(u64, u64)>, NativePhaseError> {
        if !self.journal_completed(phase, "ntfs_shrink")? {
            return Ok(None);
        }
        let resize_bytes = self.storage_plan.resize_bytes;
        // A completed shrink means the live size IS the post-shrink size, so
        // the pre-shrink size is exactly the current size plus the delta
        // that was subtracted.
        let pre_shrink = probe.size_bytes.saturating_add(resize_bytes);
        // Cross-check against the size recorded in the plan at request time:
        // on retry the plan was re-probed after the shrink, so it must agree
        // with the live probe. A mismatch means the partition moved under us.
        if let Some(recorded) = self.storage_plan.pre_shrink_bytes {
            if recorded.abs_diff(probe.size_bytes) > sector_size {
                return Err(NativePhaseError::Execution {
                    phase,
                    message: "NTFS partition size changed since the install started; refusing to resume or repeat the shrink"
                        .to_string(),
                });
            }
        }
        let target_size =
            pre_shrink
                .checked_sub(resize_bytes)
                .ok_or_else(|| NativePhaseError::Execution {
                    phase,
                    message: "NTFS shrink journal is inconsistent with the install plan"
                        .to_string(),
                })?;
        // Already at or past the target size?
        if probe.size_bytes > target_size.saturating_add(sector_size) {
            // The journal claims a completed shrink but the partition is
            // larger than the shrink target: fail closed instead of
            // shrinking again.
            return Err(NativePhaseError::Execution {
                phase,
                message: "NTFS shrink was recorded as complete but the partition is larger than the shrink target; refusing to shrink again"
                    .to_string(),
            });
        }
        let new_end = probe
            .start_bytes
            .checked_add(probe.size_bytes)
            .ok_or_else(|| NativePhaseError::Execution {
                phase,
                message: "NTFS partition geometry overflowed".to_string(),
            })?;
        let old_end = probe.start_bytes.checked_add(pre_shrink).ok_or_else(|| {
            NativePhaseError::Execution {
                phase,
                message: "NTFS target geometry overflowed".to_string(),
            }
        })?;
        if old_end <= new_end {
            return Err(NativePhaseError::Execution {
                phase,
                message: "NTFS shrink journal is inconsistent with the install plan".to_string(),
            });
        }
        const MIN_KYTHOS_BYTES: u64 = 32 * 1024 * 1024 * 1024;
        if old_end - new_end < MIN_KYTHOS_BYTES {
            return Err(NativePhaseError::Execution {
                phase,
                message: "space freed by the previous NTFS shrink is smaller than the KythOS minimum; refusing to continue"
                    .to_string(),
            });
        }
        // The adjacent freed region must still be free: if something else
        // claimed it, re-shrinking would be wrong, so fail closed.
        let free = crate::installer_storage::contains_free_region(
            snapshot,
            &self.storage_plan.disk,
            new_end,
            old_end,
            sector_size,
        )
        .map_err(|message| NativePhaseError::Execution { phase, message })?;
        if !free {
            return Err(NativePhaseError::Execution {
                phase,
                message: "space freed by the previous NTFS shrink is no longer free; refusing to shrink again"
                    .to_string(),
            });
        }
        Ok(Some((new_end, old_end)))
    }

    fn prepare_btrfs_target(
        &self,
        phase: Phase,
        cancellation: &CancellationToken,
        _target: &str,
    ) -> Result<(), NativePhaseError> {
        let _disk_lock = crate::installer_guard::acquire_disk_lock(&self.storage_plan.disk)
            .map_err(|message| NativePhaseError::Execution { phase, message })?;
        self.validate_target_disk(phase)?;
        // Re-validate the target partition against a fresh snapshot AFTER the
        // lock is held: the `target` device name came from a pre-lock snapshot,
        // and a non-cooperating process in the live session could have changed
        // what that device name refers to in the gap. Format the re-probed name.
        let target = {
            let requested = self
                .storage_plan
                .target_partition
                .as_deref()
                .ok_or_else(|| NativePhaseError::Execution {
                    phase,
                    message: "filesystem install has no target partition".to_string(),
                })?;
            let role = if self.storage_plan.mode == "manual" {
                "root partition"
            } else {
                "target partition"
            };
            let snapshot = self.disk_snapshot(phase, &self.storage_plan.disk)?;
            crate::installer_storage::validate_replace_target(
                &snapshot,
                &self.storage_plan.disk,
                requested,
                role,
                self.disk_sector_size(phase)?,
            )
            .map_err(|message| NativePhaseError::Execution { phase, message })?
            .name
        };
        // H4: durable format markers around the destructive format.
        self.record_journal(phase, "format", OpState::Started)?;
        self.execute_disk_helper(
            phase,
            cancellation,
            &serde_json::json!({
                "operation": "format_filesystem",
                "device": target,
                "fs": "btrfs",
                "label": "KythOS"
            }),
        )?;
        self.record_journal(phase, "format", OpState::Completed)?;
        self.execute_disk_helper(
            phase,
            cancellation,
            &serde_json::json!({
                "operation": "ensure_directory",
                "path": BTRFS_STAGING_MOUNTPOINT
            }),
        )?;
        self.execute_disk_helper(
            phase,
            cancellation,
            &serde_json::json!({
                "operation": "mount_filesystem",
                "device": target,
                "mountpoint": BTRFS_STAGING_MOUNTPOINT
            }),
        )?;
        self.register_mount(BTRFS_STAGING_MOUNTPOINT)?;

        let temporary_setup = (|| {
            for name in ["@", "@home"] {
                self.execute_disk_helper(
                    phase,
                    cancellation,
                    &serde_json::json!({
                        "operation": "btrfs_subvolume_create",
                        "mountpoint": BTRFS_STAGING_MOUNTPOINT,
                        "name": name
                    }),
                )?;
            }
            self.execute_disk_helper(
                phase,
                cancellation,
                &serde_json::json!({
                    "operation": "btrfs_subvolume_set_default",
                    "mountpoint": BTRFS_STAGING_MOUNTPOINT,
                    "name": "@"
                }),
            )
        })();
        let cleanup_result = self.execute_disk_helper(
            phase,
            &CancellationToken::default(),
            &serde_json::json!({
                "operation": "unmount_filesystem",
                "mountpoint": BTRFS_STAGING_MOUNTPOINT,
                "recursive": true,
                "lazy": true
            }),
        );
        self.release_mount(BTRFS_STAGING_MOUNTPOINT)?;
        temporary_setup?;
        cleanup_result?;

        self.execute_disk_helper(
            phase,
            cancellation,
            &serde_json::json!({
                "operation": "ensure_directory",
                "path": FILESYSTEM_STAGING_MOUNTPOINT
            }),
        )?;
        self.execute_disk_helper(
            phase,
            cancellation,
            &serde_json::json!({
                "operation": "mount_filesystem",
                "device": target,
                "mountpoint": FILESYSTEM_STAGING_MOUNTPOINT,
                "options": ["subvol=@"]
            }),
        )?;
        self.register_mount(FILESYSTEM_STAGING_MOUNTPOINT)?;

        self.mount_efi(phase, cancellation)?;
        Ok(())
    }

    fn mount_efi(
        &self,
        phase: Phase,
        cancellation: &CancellationToken,
    ) -> Result<(), NativePhaseError> {
        let snapshot = self.disk_snapshot(phase, &self.storage_plan.disk)?;
        let sector_size = self.disk_sector_size(phase)?;
        let Some(efi) = crate::installer_storage::efi_partition_from_snapshot(
            &snapshot,
            &self.storage_plan.disk,
            sector_size,
        )
        .map_err(|message| NativePhaseError::Execution { phase, message })?
        else {
            // L2: preflight required an ESP for every non-wipe mode. If it is
            // gone now, something changed the disk under us; silently
            // continuing without an ESP would install an unbootable system.
            return Err(NativePhaseError::Execution {
                phase,
                message: "ESP vanished between preflight and mount".to_string(),
            });
        };
        let mountpoint = format!("{FILESYSTEM_STAGING_MOUNTPOINT}/boot/efi");
        self.execute_disk_helper(
            phase,
            cancellation,
            &serde_json::json!({
                "operation": "ensure_directory",
                "path": mountpoint
            }),
        )?;
        self.execute_disk_helper(phase, cancellation, &efi_mount_operation(&efi, &mountpoint))?;
        self.register_mount(&mountpoint)?;
        Ok(())
    }

    fn execute_storage(
        &self,
        phase: Phase,
        cancellation: &CancellationToken,
    ) -> Result<(), NativePhaseError> {
        if self.storage_plan.mode != "wipe" {
            self.validate_target_disk(phase)?;
            self.check_storage_preflight(phase)?;
        }
        // H4: open the durable crash-recovery journal before the first
        // destructive mutation of the Storage phase (for wipe mode the
        // destructive step is bootc in the Image phase, but the journal is
        // still opened here so image_write has a marker).
        self.open_durable_journal(phase)?;
        let target = match self.storage_plan.mode.as_str() {
            "wipe" => {
                // bootc to-disk owns the complete wipe layout and is run in
                // the image phase; there is no separate storage mutation.
                return Ok(());
            }
            "alongside" | "manual" => {
                let requested = self
                    .storage_plan
                    .target_partition
                    .as_deref()
                    .ok_or_else(|| NativePhaseError::Execution {
                        phase,
                        message: "filesystem install has no target partition".to_string(),
                    })?;
                // prepare_btrfs_target formats this partition. Every gate
                // above validates `disk`; re-check the partition itself
                // (on that disk, not the ESP, unmounted, big enough, not
                // holding someone's data) against a fresh snapshot.
                let role = if self.storage_plan.mode == "manual" {
                    "root partition"
                } else {
                    "target partition"
                };
                let sector_size = self.disk_sector_size(phase)?;
                let snapshot = self.disk_snapshot(phase, &self.storage_plan.disk)?;
                if self.storage_plan.mode == "alongside" {
                    // Unlike free-space/NTFS-shrink, alongside never creates
                    // a BIOS boot partition. A missing /sys/firmware/efi
                    // reads as legacy BIOS: the stricter answer.
                    crate::installer_storage::validate_alongside_bios_boot(
                        &snapshot,
                        &self.storage_plan.disk,
                        std::path::Path::new("/sys/firmware/efi").exists(),
                        sector_size,
                    )
                    .map_err(|message| NativePhaseError::Execution { phase, message })?;
                }
                crate::installer_storage::validate_replace_target(
                    &snapshot,
                    &self.storage_plan.disk,
                    requested,
                    role,
                    sector_size,
                )
                .map_err(|message| NativePhaseError::Execution { phase, message })?
                .name
            }
            "free_space" => {
                let start = self.storage_plan.free_region_start.ok_or_else(|| {
                    NativePhaseError::Execution {
                        phase,
                        message: "free-space install has no selected region".to_string(),
                    }
                })?;
                let end = self.storage_plan.free_region_end.ok_or_else(|| {
                    NativePhaseError::Execution {
                        phase,
                        message: "free-space install has no selected region end".to_string(),
                    }
                })?;
                let snapshot = self.disk_snapshot(phase, &self.storage_plan.disk)?;
                // H1: the real sector size from `blockdev --getss`,
                // validated, instead of a hardcoded 512.
                let sector_size = self.disk_sector_size(phase)?;
                if !crate::installer_storage::contains_free_region(
                    &snapshot,
                    &self.storage_plan.disk,
                    start,
                    end,
                    sector_size,
                )
                .map_err(|message| NativePhaseError::Execution { phase, message })?
                {
                    return Err(NativePhaseError::Execution {
                        phase,
                        message: "selected free space is no longer available".to_string(),
                    });
                }
                // H4: durable partition_table markers around the guarded
                // table mutation. A Started record without Completed tells a
                // retry the mutation did not finish.
                self.record_journal(phase, "partition_table", OpState::Started)?;
                let result = self.guarded_table_mutation(phase, || {
                    self.create_target_partition(phase, cancellation, start, end, sector_size)
                });
                if result.is_ok() {
                    self.record_journal(phase, "partition_table", OpState::Completed)?;
                }
                result?
            }
            "resize_ntfs" => {
                self.record_journal(phase, "partition_table", OpState::Started)?;
                let result = self
                    .guarded_table_mutation(phase, || self.resize_ntfs_target(phase, cancellation));
                if result.is_ok() {
                    self.record_journal(phase, "partition_table", OpState::Completed)?;
                }
                result?
            }
            _ => {
                return Err(NativePhaseError::InvalidPlan {
                    phase,
                    operation: NativeOperation::StorageMutation,
                });
            }
        };
        self.prepare_btrfs_target(phase, cancellation, &target)?;
        *self
            .storage_target
            .lock()
            .map_err(|_| NativePhaseError::Execution {
                phase,
                message: "native storage target state is unavailable".to_string(),
            })? = Some(target);
        Ok(())
    }

    fn execute_secure_boot(
        &self,
        phase: Phase,
        cancellation: &CancellationToken,
    ) -> Result<(), NativePhaseError> {
        let plan = crate::installer_secure_boot::stage_with_cancellation(
            crate::installer_secure_boot::SecureBootStageInput {
                kernel: self.secure_boot_kernel.clone(),
                force_stage: self.secure_boot_force_stage,
                // The stage input boundary stays String (the secure-boot
                // side wraps its copy in Zeroizing internally); the
                // executor's retained copy above is the one zeroized here.
                password: self.secure_boot_password.to_string(),
            },
            || cancellation.is_cancelled(),
        )
        .map_err(|message| NativePhaseError::Execution { phase, message })?;
        *self
            .secure_boot_state
            .lock()
            .map_err(|_| NativePhaseError::Execution {
                phase,
                message: "native Secure Boot state is unavailable".to_string(),
            })? = Some(plan.state.clone());
        if plan.state == "failed" {
            return Err(NativePhaseError::Execution {
                phase,
                message: plan.message,
            });
        }
        Ok(())
    }

    fn execute_complete(&self, phase: Phase) -> Result<(), NativePhaseError> {
        self.cleanup_mounts(phase)
            .map_err(|message| NativePhaseError::Execution { phase, message })?;
        self.write_transaction(
            "complete",
            phase,
            "done",
            "Native installer completed successfully",
        )
        .map_err(|message| NativePhaseError::Execution { phase, message })
    }

    /// Build a native supervisor for the daemon's route integration.
    pub(crate) fn into_supervisor(self) -> JobSupervisor<Self> {
        JobSupervisor::new(self)
    }
}

impl PhaseExecutor for NativePhaseExecutor {
    fn execute_phase(&self, phase: Phase, cancellation: &CancellationToken) -> Result<(), String> {
        self.execute_phase_typed(phase, cancellation)
            .map_err(|error| error.to_string())
    }

    fn record_job_started(&self, job_id: u64) -> Result<(), String> {
        self.transaction
            .lock()
            .map_err(|_| "native transaction state is unavailable".to_string())?
            .job_id = Some(job_id);
        Ok(())
    }

    fn record_cancelled(&self, phase: Option<Phase>) {
        let _ = self.cleanup_mounts(phase.unwrap_or(Phase::Prepare));
        let message = super::installer_job::CANCELLATION_MESSAGE;
        self.write_terminal_transaction(phase, message);
        self.persist_failure_summary(message);
    }

    fn record_failed(&self, phase: Phase, message: &str) {
        let _ = self.cleanup_mounts(phase);
        self.write_terminal_transaction(Some(phase), message);
        self.persist_failure_summary(message);
    }

    fn success_mok_state(&self) -> Option<String> {
        self.secure_boot_state
            .lock()
            .ok()
            .and_then(|state| state.clone())
    }
}

/// M5: capture the selected disk's MODEL / SERIAL / SIZE (bytes) from lsblk
/// at request-selection time. Best-effort: any probe failure yields `None`
/// fields rather than blocking the install.
fn probe_disk_identity(disk: &str) -> (Option<String>, Option<String>, Option<u64>) {
    const NO_IDENTITY: (Option<String>, Option<String>, Option<u64>) = (None, None, None);
    let disk = match installer_plan::normalize_device_path(disk) {
        Some(disk) => disk,
        None => return NO_IDENTITY,
    };
    let output = match Command::new("/usr/bin/lsblk")
        .args([
            "--json",
            "--bytes",
            "--nodeps",
            "--output",
            "MODEL,SERIAL,SIZE",
            &disk,
        ])
        .output()
    {
        Ok(output) if output.status.success() => output,
        _ => return NO_IDENTITY,
    };
    let snapshot: serde_json::Value = match serde_json::from_slice(&output.stdout) {
        Ok(snapshot) => snapshot,
        Err(_) => return NO_IDENTITY,
    };
    let device = match snapshot
        .get("blockdevices")
        .and_then(|devices| devices.as_array())
        .and_then(|devices| devices.first())
    {
        Some(device) => device,
        None => return NO_IDENTITY,
    };
    let text_field = |name: &str| {
        device
            .get(name)
            .and_then(|value| value.as_str())
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .map(|value| value.chars().take(256).collect::<String>())
    };
    let size = device
        .get("size")
        .and_then(|value| {
            value.as_u64().or_else(|| {
                value
                    .as_str()
                    .and_then(|value| value.trim().parse::<u64>().ok())
            })
        })
        .filter(|size| *size > 0);
    (text_field("model"), text_field("serial"), size)
}

/// H2: best-effort live size of one partition, used to record the
/// pre-shrink size in the plan before any destructive step.
fn probe_partition_size_bytes(disk: &str, partition: &str) -> Option<u64> {
    let sector_size = probe_sector_size(disk)?;
    let output = Command::new("/usr/bin/lsblk")
        .args([
            "--json",
            "--bytes",
            "--paths",
            "--output",
            "NAME,SIZE,TYPE,PARTN",
            disk,
        ])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let snapshot = String::from_utf8(output.stdout).ok()?;
    crate::installer_storage::partition_probe_from_snapshot(&snapshot, disk, partition, sector_size)
        .ok()
        .map(|probe| probe.size_bytes)
        .filter(|size| *size > 0)
}

/// Best-effort sector-size probe for contexts without an executor.
/// Mirrors the storage layer's `valid_sector_size`: powers of two from
/// 512-byte classic sectors through 4096-byte 4Kn sectors.
fn probe_sector_size(disk: &str) -> Option<u64> {
    let output = Command::new("/usr/sbin/blockdev")
        .args(["--getss", disk])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let size: u64 = String::from_utf8(output.stdout).ok()?.trim().parse().ok()?;
    if !size.is_power_of_two() || !(512..=4096).contains(&size) {
        return None;
    }
    Some(size)
}

/// L5: best-effort whole-disk size in bytes.
fn probe_disk_size_bytes(disk: &str) -> Option<u64> {
    let output = Command::new("/usr/bin/lsblk")
        .args(["--json", "--bytes", "--nodeps", "--output", "SIZE", disk])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let snapshot: serde_json::Value = serde_json::from_slice(&output.stdout).ok()?;
    snapshot
        .get("blockdevices")
        .and_then(|devices| devices.as_array())
        .and_then(|devices| devices.first())
        .and_then(|device| device.get("size"))
        .and_then(|value| {
            value.as_u64().or_else(|| {
                value
                    .as_str()
                    .and_then(|value| value.trim().parse::<u64>().ok())
            })
        })
        .filter(|size| *size > 0)
}

/// M6: `sha256:` followed by exactly 64 hex digits.
fn is_sha256_digest(value: &str) -> bool {
    value.len() == 71
        && value.starts_with("sha256:")
        && value[7..].bytes().all(|byte| byte.is_ascii_hexdigit())
}

/// M6: read a small trusted metadata file: absolute path, no parent
/// traversal, a regular file (never a symlink), size-capped.
fn read_regular_file(path: &Path) -> Result<Vec<u8>, String> {
    if !path.is_absolute()
        || path
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return Err(format!("{} is not a safe absolute path", path.display()));
    }
    let metadata = std::fs::symlink_metadata(path)
        .map_err(|error| format!("could not inspect {}: {error}", path.display()))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(format!(
            "{} is missing or not a regular file",
            path.display()
        ));
    }
    if metadata.len() > 4 * 1024 * 1024 {
        return Err(format!("{} is too large", path.display()));
    }
    std::fs::read(path).map_err(|error| format!("could not read {}: {error}", path.display()))
}

fn read_json_file(path: &Path) -> Result<serde_json::Value, String> {
    let raw = read_regular_file(path)?;
    serde_json::from_slice(&raw)
        .map_err(|error| format!("{} is not valid JSON: {error}", path.display()))
}

fn sha256_file_hex(path: &Path) -> Result<String, String> {
    let output = Command::new("/usr/bin/sha256sum")
        .arg(path)
        .output()
        .map_err(|error| format!("could not hash {}: {error}", path.display()))?;
    if !output.status.success() {
        return Err(format!("could not hash {}", path.display()));
    }
    String::from_utf8(output.stdout)
        .map_err(|_| "sha256sum returned non-UTF-8 output".to_string())?
        .split_whitespace()
        .next()
        .map(str::to_string)
        .filter(|hex| hex.len() == 64 && hex.bytes().all(|byte| byte.is_ascii_hexdigit()))
        .ok_or_else(|| "sha256sum returned no digest".to_string())
}

/// M10: snapshot `efibootmgr -v` as (boot-number, label) pairs. Best-effort:
/// `None` when efibootmgr is unavailable (e.g. legacy BIOS boot).
fn snapshot_boot_entries() -> Option<Vec<(String, String)>> {
    for program in ["/usr/sbin/efibootmgr", "/usr/bin/efibootmgr"] {
        let output = Command::new(program).arg("-v").output().ok()?;
        if !output.status.success() {
            continue;
        }
        let text = String::from_utf8(output.stdout).ok()?;
        return Some(parse_boot_entries(&text));
    }
    None
}

/// Parse `BootNNNN[*] label` lines; the boot number is the stable identity.
fn parse_boot_entries(text: &str) -> Vec<(String, String)> {
    text.lines()
        .filter_map(|line| {
            let rest = line.trim().strip_prefix("Boot")?;
            if rest.len() < 4 {
                return None;
            }
            let (number, tail) = rest.split_at(4);
            if !number.bytes().all(|byte| byte.is_ascii_hexdigit()) {
                return None;
            }
            let label = tail.trim_start_matches(['*', ' ', '\t']).trim().to_string();
            Some((number.to_ascii_uppercase(), label))
        })
        .collect()
}

/// L5: free bytes available to unprivileged writers on `path`'s filesystem.
fn statvfs_available_bytes(path: &str) -> Option<u64> {
    let cpath = std::ffi::CString::new(path).ok()?;
    let mut stat: libc::statvfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::statvfs(cpath.as_ptr(), &mut stat) } != 0 {
        return None;
    }
    Some((stat.f_bavail as u64).saturating_mul(stat.f_frsize as u64))
}

/// L5: MemAvailable from /proc/meminfo, in bytes.
fn mem_available_bytes() -> Option<u64> {
    let content = std::fs::read_to_string("/proc/meminfo").ok()?;
    for line in content.lines() {
        if let Some(rest) = line.strip_prefix("MemAvailable:") {
            let kilobytes: u64 = rest.split_whitespace().next()?.parse().ok()?;
            return Some(kilobytes.saturating_mul(1024));
        }
    }
    None
}

/// L5: measure an embedded OCI layout's image size by summing its manifest
/// layer sizes. Mirrors the layout parsing in installer_readonly.rs.
fn oci_layout_bytes(reference: &str) -> Option<u64> {
    const MAX_META_BYTES: u64 = 4 * 1024 * 1024;
    let rest = reference.strip_prefix("oci:")?;
    // Split "path:tag": the tag is the last ':' after the last '/'.
    let (root, tag) = match rest.rfind('/') {
        Some(slash) => match rest[slash..].rfind(':') {
            Some(relative) => (&rest[..slash + relative], &rest[slash + relative + 1..]),
            None => (rest, "latest"),
        },
        None => match rest.rfind(':') {
            Some(colon) => (&rest[..colon], &rest[colon + 1..]),
            None => (rest, "latest"),
        },
    };
    if root.is_empty() || tag.is_empty() {
        return None;
    }
    let root_path = Path::new(root);
    if !root_path.is_absolute()
        || root_path
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return None;
    }
    let read_capped = |path: &Path| -> Option<Vec<u8>> {
        let metadata = std::fs::symlink_metadata(path).ok()?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return None;
        }
        if metadata.len() > MAX_META_BYTES {
            return None;
        }
        std::fs::read(path).ok()
    };
    let index: serde_json::Value =
        serde_json::from_slice(&read_capped(&root_path.join("index.json"))?).ok()?;
    let manifests = index.get("manifests")?.as_array()?;
    let descriptor = manifests
        .iter()
        .find(|item| {
            item.get("annotations")
                .and_then(|value| value.as_object())
                .and_then(|annotations| annotations.get("org.opencontainers.image.ref.name"))
                .and_then(|value| value.as_str())
                == Some(tag)
        })
        .or_else(|| (manifests.len() == 1).then(|| &manifests[0]))?;
    let hex = descriptor
        .get("digest")?
        .as_str()?
        .strip_prefix("sha256:")?;
    if hex.len() != 64 || !hex.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return None;
    }
    let manifest: serde_json::Value = serde_json::from_slice(&read_capped(
        &root_path.join("blobs").join("sha256").join(hex),
    )?)
    .ok()?;
    let mut total: u64 = 0;
    for layer in manifest.get("layers")?.as_array()? {
        total = total.saturating_add(layer.get("size")?.as_u64()?);
    }
    if let Some(config_size) = manifest
        .get("config")
        .and_then(|config| config.get("size"))
        .and_then(|size| size.as_u64())
    {
        total = total.saturating_add(config_size);
    }
    if total == 0 {
        None
    } else {
        Some(total)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::installer_accounts::CreateUserInput;
    use crate::installer_bootc::BootcInstallInput;
    use crate::installer_configuration::ConfigurationInput;
    use crate::installer_secure_boot::SecureBootInput;

    #[test]
    fn erase_disk_install_always_passes_wipe_to_bootc() {
        // Neither frontend sends a `wipe` key (native_main.rs as_request,
        // the web InstallRequest type). bootc install to-disk refuses a disk
        // with existing partitions unless --wipe is passed ("Detected
        // existing partitions on ...; use e.g. `wipefs` or --wipe"), so the
        // default "Erase full disk" mode must imply it, as Python did.
        let request = NativeInstallRequest::from_http(serde_json::json!({
            "disk": "sda",
            "install_mode": "wipe",
            "acknowledged_irreversible": true,
        }))
        .expect("frontend request should decode");
        assert!(request.execution.bootc.wipe);
        let plan = crate::installer_bootc::build_plan(request.execution.bootc)
            .expect("bootc plan validates");
        assert!(
            plan.argv.iter().any(|arg| arg == "--wipe"),
            "{:?}",
            plan.argv
        );

        // Filesystem installs write into a prepared mountpoint and never
        // wipe the disk.
        let alongside = NativeInstallRequest::from_http(serde_json::json!({
            "disk": "sda",
            "install_mode": "alongside",
            "target_partition": "sda3",
            "wipe": true,
            "acknowledged_irreversible": true,
        }))
        .expect("frontend request should decode");
        assert!(!alongside.execution.bootc.wipe);
    }

    #[test]
    fn filesystem_installs_skip_bootc_finalize() {
        // Without --skip-finalize, bootc to-filesystem ends by remounting
        // the target read-only ("finally mounting it readonly"), and the
        // configuration phase that follows must write hostname, locale,
        // fstab, and the user account into that same filesystem. No
        // frontend sends `skip_finalize`; Python always passed it here.
        for (mode, extra) in [
            ("alongside", serde_json::json!({"target_partition": "sda3"})),
            (
                "free_space",
                serde_json::json!({"free_region_start": 1048576, "free_region_end": 68720525312_i64}),
            ),
            (
                "resize_ntfs",
                serde_json::json!({"resize_partition": "sda2", "resize_gib": 64}),
            ),
            ("manual", serde_json::json!({"target_partition": "sda3"})),
        ] {
            let mut body = serde_json::json!({
                "disk": "sda",
                "install_mode": mode,
                "acknowledged_irreversible": true,
            });
            for (key, value) in extra.as_object().unwrap() {
                body[key] = value.clone();
            }
            let request = NativeInstallRequest::from_http(body).expect(mode);
            assert!(request.execution.bootc.skip_finalize, "{mode}");
            assert_eq!(
                request.execution.bootc.target,
                FILESYSTEM_STAGING_MOUNTPOINT
            );
            assert_eq!(
                request.execution.configuration.target_root,
                FILESYSTEM_STAGING_MOUNTPOINT
            );
            let plan = crate::installer_bootc::build_plan(request.execution.bootc).expect(mode);
            assert!(
                plan.argv.iter().any(|arg| arg == "--skip-finalize"),
                "{mode}: {:?}",
                plan.argv
            );
        }
        let wipe = NativeInstallRequest::from_http(serde_json::json!({
            "disk": "sda",
            "install_mode": "wipe",
            "acknowledged_irreversible": true,
        }))
        .expect("wipe request decodes");
        assert_eq!(
            wipe.execution.configuration.target_root,
            WIPE_STAGING_MOUNTPOINT
        );
        let plan = crate::installer_bootc::build_plan(wipe.execution.bootc).expect("wipe plan");
        assert!(!plan.argv.iter().any(|arg| arg == "--skip-finalize"));
    }

    #[test]
    fn every_mode_that_creates_home_subvolume_mounts_it() {
        // free_space and resize_ntfs build the same @/@home layout as
        // alongside; skipping alongside-home for them left @home empty and
        // unmounted, with /var/home silently living inside @.
        for mode in ["alongside", "free_space", "resize_ntfs"] {
            assert!(lays_out_home_subvolume(mode), "{mode}");
        }
        // wipe: bootc to-disk owns the layout. manual: /home comes from the
        // user's own manual mounts.
        for mode in ["wipe", "manual"] {
            assert!(!lays_out_home_subvolume(mode), "{mode}");
        }
    }

    #[test]
    fn efi_mount_requests_build_through_the_disk_helper() {
        use crate::installer_disk::{build_plan, DiskOperationInput};
        use crate::installer_storage::EfiPartition;
        let mountpoint = format!("{FILESYSTEM_STAGING_MOUNTPOINT}/boot/efi");
        let plan = |efi: &EfiPartition| {
            let input: DiskOperationInput =
                serde_json::from_value(efi_mount_operation(efi, &mountpoint))
                    .expect("request decodes");
            build_plan(input).map(|plan| plan.argv)
        };
        // An ESP the live session already mounted must bind-mount, not be
        // rejected as a non-/dev "device" after the target was formatted.
        let mounted = EfiPartition {
            name: "/dev/sda1".into(),
            mounted_at: Some("/mnt/esp".into()),
        };
        assert_eq!(
            plan(&mounted).expect("bind mount validates"),
            ["/usr/sbin/mount", "--bind", "/mnt/esp", &mountpoint]
        );
        let unmounted = EfiPartition {
            name: "/dev/sda1".into(),
            mounted_at: None,
        };
        assert_eq!(
            plan(&unmounted).expect("device mount validates"),
            ["/usr/sbin/mount", "/dev/sda1", &mountpoint]
        );
    }

    #[test]
    fn run_guarded_skips_restore_on_success() {
        let mut restore_calls = 0;
        let result: Result<i32, (&str, Option<&str>)> = NativePhaseExecutor::run_guarded(
            || Ok(42),
            || {
                restore_calls += 1;
                Ok(())
            },
        );
        assert_eq!(result, Ok(42));
        assert_eq!(restore_calls, 0, "restore must not run on success");
    }

    #[test]
    fn run_guarded_restores_on_failure_and_preserves_the_original_error() {
        // The guided-install partition-create/resize-NTFS paths lost their
        // partition-table backup/restore safety net in the Rust port (the
        // manual Journal commit kept it) — Python's `PartitionTableGuard`
        // always restores on any failure inside the guarded scope. A failing
        // restore (e.g. the disk helper itself errors) must never mask what
        // actually broke the mutation.
        let mut restore_ran = false;
        let restore_outcome: Result<(), &str> = Err("restore also failed");
        let result: Result<i32, (&str, Option<&str>)> = NativePhaseExecutor::run_guarded(
            || Err("original failure"),
            || {
                restore_ran = true;
                restore_outcome
            },
        );
        assert_eq!(
            result,
            Err(("original failure", Some("restore also failed"))),
            "both the operation and restore failures must be reported"
        );
        assert!(restore_ran, "restore must run exactly once on failure");
    }

    fn request(with_account: bool) -> NativeInstallRequest {
        NativeInstallRequest {
            storage: InstallerPlanInput {
                disk: "sda".into(),
                install_mode: "wipe".into(),
                target_partition: String::new(),
                resize_partition: String::new(),
                resize_gib: 0,
                free_region_start: 0,
                free_region_end: 0,
                target_disk_serial: None,
                target_disk_model: None,
                target_disk_size_bytes: None,
            },
            execution: InstallerExecutionInput {
                bootc: BootcInstallInput {
                    subcommand: "to-disk".into(),
                    source_imgref: "oci:/usr/share/kyth/image:latest".into(),
                    target_imgref: "ghcr.io/kyth-os/kyth:latest".into(),
                    target: "/dev/sda".into(),
                    skip_fetch_check: false,
                    skip_finalize: false,
                    root_subvolume: false,
                    wipe: true,
                    encryption: "none".into(),
                    tpm_recovery_ack: false,
                },
                configuration: ConfigurationInput {
                    target_root: "/mnt/target".into(),
                    hostname: "kyth".into(),
                    timezone: "UTC".into(),
                    locale: "en_US.UTF-8".into(),
                    keymap: "us".into(),
                },
                account: with_account.then_some(CreateUserInput {
                    deploy_root: "/mnt/deploy".into(),
                    target_root: "/mnt/target".into(),
                    username: "kyth_user".into(),
                    password_hash: "$6$secret-must-not-leak".into(),
                }),
                secure_boot: SecureBootInput {
                    kernel: "fedora".into(),
                    force_stage: false,
                    certificate_present: false,
                    mokutil_present: false,
                    secure_boot: "unknown".into(),
                    enrolled: "unknown".into(),
                    pending: "unknown".into(),
                },
            },
            manual_mounts: None,
            secure_boot_password: String::new(),
            transaction_path: "/run/kyth-installer/txn/transaction.json".into(),
        }
    }

    #[test]
    fn frontend_encryption_choice_reaches_bootc_request() {
        let request = NativeInstallRequest::from_http(serde_json::json!({
            "disk": "sda",
            "encryption": "tpm2",
            "acknowledged-irreversible": true,
        }))
        .expect("frontend request should decode");
        assert_eq!(request.execution.bootc.encryption, "tpm2");

        let default = NativeInstallRequest::from_http(serde_json::json!({
            "disk": "sda",
            "acknowledged_irreversible": true,
        }))
        .expect("frontend request should decode");
        assert_eq!(default.execution.bootc.encryption, "none");
    }

    #[test]
    fn manual_mount_assignments_survive_http_request_projection() {
        let request = NativeInstallRequest::from_http(serde_json::json!({
            "disk": "/dev/sda",
            "install_mode": "manual",
            "target_partition": "/dev/sda2",
            "acknowledged_irreversible": true,
            "uuid": "test-manual-uuid",
            "mounts": [{
                "partition": "/dev/sda3",
                "mountpoint": "/home",
                "fstype": "btrfs"
            }]
        }))
        .expect("manual request should parse");
        let mounts = request
            .manual_mounts
            .expect("manual mounts should be retained");
        assert_eq!(mounts.mounts.len(), 1);
        assert_eq!(mounts.mounts[0].partition, "/dev/sda3");
        assert_eq!(mounts.mounts[0].mountpoint, "/home");
        assert_eq!(mounts.mounts[0].fstype, "btrfs");
    }

    #[test]
    fn unsupported_encryption_fails_before_any_worker_starts() {
        let mut bad = request(false);
        bad.execution.bootc.encryption = "luks".into();
        let error = NativePhaseExecutor::from_request(bad)
            .err()
            .expect("unsupported encryption must fail closed");
        assert!(
            error.contains("encryption unsupported"),
            "unexpected error: {error}"
        );
    }

    #[test]
    fn frontend_cachyos_kernel_alias_is_normalized_for_native_secure_boot() {
        let request = NativeInstallRequest::from_http(serde_json::json!({
            "kernel": " CachyOS ",
            "acknowledged-irreversible": true,
        }))
        .expect("frontend request should decode");

        assert_eq!(request.execution.secure_boot.kernel, "cachy");
    }

    #[test]
    fn start_without_irreversible_acknowledgement_fails_closed() {
        let error = NativeInstallRequest::from_http(serde_json::json!({
            "disk": "sda",
        }))
        .err()
        .expect("missing ack must fail closed");
        assert!(
            error.contains("irreversible step is acknowledged"),
            "unexpected error: {error}"
        );
        // Either spelling satisfies the gate (Slint vs web frontend).
        for key in ["acknowledged-irreversible", "acknowledged_irreversible"] {
            let mut body = serde_json::Map::new();
            body.insert("disk".to_string(), serde_json::json!("sda"));
            body.insert(key.to_string(), serde_json::json!(true));
            NativeInstallRequest::from_http(serde_json::Value::Object(body))
                .expect("ack spelling should decode");
        }
    }

    #[test]
    fn image_phase_refuses_unverifiable_embedded_source_before_bootc() {
        let mut missing = request(false);
        missing.execution.bootc.source_imgref = "oci:/nonexistent/kyth/image:latest".into();
        let executor =
            NativePhaseExecutor::from_request(missing).expect("request shape should validate");
        let error = executor
            .verify_install_source(Phase::Image)
            .expect_err("missing embedded image must refuse bootc");
        assert!(
            error.to_string().contains("refusing bootc install"),
            "{error}"
        );
    }

    #[test]
    fn image_phase_refuses_unpinned_docker_source() {
        // M6: a tag-based docker:// reference is mutable after the ISO was
        // built, so it can no longer pass through to fetch-time checks: it
        // must be digest-pinned and verified before bootc runs.
        let mut network = request(false);
        network.execution.bootc.source_imgref = "docker://ghcr.io/kyth-os/kyth:testing".into();
        let executor =
            NativePhaseExecutor::from_request(network).expect("request shape should validate");
        let error = executor
            .verify_install_source(Phase::Image)
            .expect_err("unpinned docker source must fail closed");
        assert!(error.to_string().contains("digest-pinned"), "{error}");
    }

    /// Set up a digest-pinned docker source test: temp ISO metadata +
    /// signature bundle, env pins pointed at them. Returns the previous env
    /// values for restoration.
    fn pinned_docker_fixture(
        digest_hex: &str,
    ) -> (
        tempfile::TempDir,
        (Option<String>, Option<String>, Option<String>),
    ) {
        let dir = tempfile::tempdir().expect("temporary source metadata");
        let digest = format!("sha256:{digest_hex}");
        let bundle_path = dir.path().join("image.sig.bundle.json");
        std::fs::write(
            &bundle_path,
            serde_json::to_string(&serde_json::json!({
                "schema_version": 1,
                "digest": digest,
                "release_digest": digest,
                "source_image": format!("docker://ghcr.io/kyth-os/kyth@{digest}"),
                "identity": "test",
                "issuer": "test",
                "signatures": ["dGVzdA=="],
            }))
            .unwrap(),
        )
        .unwrap();
        let bundle_sha = {
            let output = std::process::Command::new("/usr/bin/sha256sum")
                .arg(&bundle_path)
                .output()
                .expect("sha256sum should run");
            assert!(output.status.success());
            String::from_utf8(output.stdout)
                .unwrap()
                .split_whitespace()
                .next()
                .unwrap()
                .to_string()
        };
        let metadata_path = dir.path().join("image-source.json");
        std::fs::write(
            &metadata_path,
            serde_json::to_string(&serde_json::json!({
                "schema_version": 1,
                "digest": digest,
                "release_digest": digest,
                "target_image": "ghcr.io/kyth-os/kyth:latest",
                "source_image": format!("docker://ghcr.io/kyth-os/kyth@{digest}"),
                "signature": "verified",
                "signature_digest": format!("sha256:{bundle_sha}"),
            }))
            .unwrap(),
        )
        .unwrap();
        let old = (
            std::env::var("KYTH_SOURCE_DIGEST").ok(),
            std::env::var("KYTH_SOURCE_METADATA").ok(),
            std::env::var("KYTH_SOURCE_SIGNATURE").ok(),
        );
        std::env::set_var("KYTH_SOURCE_DIGEST", &digest);
        std::env::set_var("KYTH_SOURCE_METADATA", metadata_path.to_str().unwrap());
        std::env::set_var("KYTH_SOURCE_SIGNATURE", bundle_path.to_str().unwrap());
        (dir, old)
    }

    fn restore_env(old: (Option<String>, Option<String>, Option<String>)) {
        for (key, value) in [
            ("KYTH_SOURCE_DIGEST", old.0),
            ("KYTH_SOURCE_METADATA", old.1),
            ("KYTH_SOURCE_SIGNATURE", old.2),
        ] {
            match value {
                Some(value) => std::env::set_var(key, value),
                None => std::env::remove_var(key),
            }
        }
    }

    #[test]
    fn image_phase_verifies_digest_pinned_docker_source() {
        let digest_hex = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        let (_dir, old) = pinned_docker_fixture(digest_hex);
        let result = (|| {
            let mut pinned = request(false);
            pinned.execution.bootc.source_imgref =
                format!("docker://ghcr.io/kyth-os/kyth@sha256:{digest_hex}");
            let executor =
                NativePhaseExecutor::from_request(pinned).expect("request shape should validate");
            executor.verify_install_source(Phase::Image)
        })();
        restore_env(old);
        result.expect("pinned docker source matching the ISO release should verify");
    }

    #[test]
    fn image_phase_refuses_docker_source_with_mismatched_env_pin() {
        let digest_hex = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        let (_dir, old) = pinned_docker_fixture(digest_hex);
        // Tamper with the environment pin only: the reference digest no
        // longer matches KYTH_SOURCE_DIGEST.
        std::env::set_var(
            "KYTH_SOURCE_DIGEST",
            "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        );
        let result = (|| {
            let mut pinned = request(false);
            pinned.execution.bootc.source_imgref =
                format!("docker://ghcr.io/kyth-os/kyth@sha256:{digest_hex}");
            let executor =
                NativePhaseExecutor::from_request(pinned).expect("request shape should validate");
            executor.verify_install_source(Phase::Image)
        })();
        restore_env(old);
        let error = result.expect_err("mismatched env pin must fail closed");
        assert!(error.to_string().contains("KYTH_SOURCE_DIGEST"), "{error}");
    }

    #[test]
    fn image_phase_refuses_docker_source_with_tampered_bundle() {
        let digest_hex = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        let (dir, old) = pinned_docker_fixture(digest_hex);
        // Rewrite the bundle so its digest no longer matches the metadata's
        // signature_digest pin.
        std::fs::write(
            dir.path().join("image.sig.bundle.json"),
            r#"{"schema_version":1,"digest":"sha256:0000000000000000000000000000000000000000000000000000000000000000"}"#,
        )
        .unwrap();
        let result = (|| {
            let mut pinned = request(false);
            pinned.execution.bootc.source_imgref =
                format!("docker://ghcr.io/kyth-os/kyth@sha256:{digest_hex}");
            let executor =
                NativePhaseExecutor::from_request(pinned).expect("request shape should validate");
            executor.verify_install_source(Phase::Image)
        })();
        restore_env(old);
        result.expect_err("tampered bundle must fail closed");
    }

    #[test]
    fn missing_install_mode_fails_closed_at_plan_build() {
        // L3: no install_mode key means the empty default, and the plan's
        // fail-closed empty-mode check must fire instead of wiping.
        let request = NativeInstallRequest::from_http(serde_json::json!({
            "disk": "sda",
            "acknowledged_irreversible": true,
        }))
        .expect("request without a mode should decode");
        let error = NativePhaseExecutor::from_request(request)
            .err()
            .expect("empty install mode must fail closed");
        assert!(error.contains("No install mode"), "{error}");
    }

    #[test]
    fn bootc_subcommand_is_derived_from_install_mode_not_client() {
        // L17: a client-supplied `subcommand` key must never reach the bootc
        // plan; the subcommand follows strictly from the install mode.
        let wipe = NativeInstallRequest::from_http(serde_json::json!({
            "disk": "sda",
            "install_mode": "wipe",
            "subcommand": "to-filesystem",
            "acknowledged_irreversible": true,
        }))
        .expect("wipe request should decode");
        assert_eq!(wipe.execution.bootc.subcommand, "to-disk");
        let alongside = NativeInstallRequest::from_http(serde_json::json!({
            "disk": "sda",
            "install_mode": "alongside",
            "target_partition": "sda3",
            "subcommand": "to-disk",
            "acknowledged_irreversible": true,
        }))
        .expect("alongside request should decode");
        assert_eq!(alongside.execution.bootc.subcommand, "to-filesystem");
    }

    #[test]
    fn manual_request_without_uuid_fails_closed() {
        // M4: the uuid travels with the manual-mounts apply call; an empty
        // one is rejected at decode time.
        let error = NativeInstallRequest::from_http(serde_json::json!({
            "disk": "/dev/sda",
            "install_mode": "manual",
            "target_partition": "/dev/sda2",
            "acknowledged_irreversible": true,
            "mounts": [],
        }))
        .err()
        .expect("manual request without a uuid must fail closed");
        assert!(error.contains("uuid"), "{error}");
    }

    #[test]
    fn parses_efibootmgr_boot_entries() {
        let entries = parse_boot_entries(
            "BootCurrent: 0001\nTimeout: 1 seconds\nBootOrder: 0001,0000\nBoot0000* Windows Boot Manager\tHD(1,GPT,...)\nBoot0001* KythOS\nBoot000A  unnamed entry\nnot a boot line\n",
        );
        assert_eq!(
            entries,
            vec![
                (
                    "0000".to_string(),
                    "Windows Boot Manager\tHD(1,GPT,...)".to_string()
                ),
                ("0001".to_string(), "KythOS".to_string()),
                ("000A".to_string(), "unnamed entry".to_string()),
            ]
        );
        assert!(parse_boot_entries("no boot entries here").is_empty());
    }

    #[test]
    fn validates_request_and_preserves_native_operation_order() {
        let executor = NativePhaseExecutor::from_request(request(true))
            .expect("typed native install request should validate");
        assert_eq!(
            executor.operation_order(),
            vec![
                NativeOperation::ValidateStoragePlan,
                NativeOperation::ValidateExecutionPlan,
                NativeOperation::StorageMutation,
                NativeOperation::ImageWrite,
                NativeOperation::ConfigurationWrite,
                NativeOperation::AccountCreate,
                NativeOperation::SecureBootInteraction,
                NativeOperation::CompletionCommit,
            ]
        );
        assert_eq!(executor.storage_plan().mode, "wipe");
        assert_eq!(executor.execution_plan().bootc.target, "/dev/sda");
    }

    #[test]
    fn execution_plan_and_operation_diagnostics_exclude_password_hash() {
        let executor = NativePhaseExecutor::from_request(request(true))
            .expect("typed native install request should validate");
        let plan = serde_json::to_string(executor.execution_plan()).unwrap();
        let operations = executor
            .operation_order()
            .iter()
            .map(ToString::to_string)
            .collect::<Vec<_>>()
            .join(",");
        assert!(!plan.contains("secret-must-not-leak"));
        assert!(!operations.contains("secret-must-not-leak"));
    }

    #[test]
    fn skipped_secure_boot_does_not_spawn_or_retain_secret_in_plan() {
        let mut request = request(false);
        let directory = tempfile::tempdir().expect("temporary transaction directory");
        crate::installer_transaction::allow_test_transaction_base(directory.path());
        request.transaction_path = directory
            .path()
            .join("transaction.json")
            .to_string_lossy()
            .into_owned();
        request.secure_boot_password = "mok-secret-must-not-leak".into();
        let executor = NativePhaseExecutor::from_request(request)
            .expect("typed native install request should validate");
        let cancellation = CancellationToken::default();
        assert_eq!(
            executor.execute_phase_typed(Phase::SecureBoot, &cancellation),
            Ok(())
        );
        assert_eq!(
            <NativePhaseExecutor as PhaseExecutor>::success_mok_state(&executor),
            Some("skipped".to_string())
        );
        let plan = serde_json::to_string(executor.execution_plan()).unwrap();
        assert!(!plan.contains("mok-secret-must-not-leak"));
    }

    #[test]
    fn completion_writes_a_secret_free_native_transaction() {
        let directory = tempfile::tempdir().expect("temporary transaction directory");
        crate::installer_transaction::allow_test_transaction_base(directory.path());
        let mut request = request(false);
        request.transaction_path = directory
            .path()
            .join("transaction.json")
            .to_string_lossy()
            .into_owned();
        let executor = NativePhaseExecutor::from_request(request)
            .expect("typed native install request should validate");
        executor
            .execute_phase_typed(Phase::Complete, &CancellationToken::default())
            .expect("native completion should persist transaction");
        let transaction = std::fs::read_to_string(directory.path().join("transaction.json"))
            .expect("native transaction should exist");
        assert!(transaction.contains("Native installer completed successfully"));
        assert!(!transaction.contains("secret"));
    }

    #[test]
    fn preparation_persists_a_recoverable_native_transaction() {
        let directory = tempfile::tempdir().expect("temporary transaction directory");
        crate::installer_transaction::allow_test_transaction_base(directory.path());
        let mut request = request(false);
        request.transaction_path = directory
            .path()
            .join("transaction.json")
            .to_string_lossy()
            .into_owned();
        let executor = NativePhaseExecutor::from_request(request)
            .expect("typed native install request should validate");
        <NativePhaseExecutor as PhaseExecutor>::record_job_started(&executor, 42)
            .expect("job correlation should be accepted");
        executor
            .execute_phase_typed(Phase::Prepare, &CancellationToken::default())
            .expect("native preparation should persist transaction");
        let transaction: serde_json::Value = serde_json::from_str(
            &std::fs::read_to_string(directory.path().join("transaction.json"))
                .expect("native preparation transaction should exist"),
        )
        .expect("native preparation transaction should be JSON");
        assert_eq!(transaction["status"], "prepared");
        assert_eq!(transaction["phase"], "prepare");
        assert_eq!(transaction["lifecycle"], "installing");
        assert!(transaction["transaction_id"]
            .as_str()
            .is_some_and(|id| { id.starts_with("native-") }));
        assert_eq!(transaction["job_id"], 42);
        assert_eq!(transaction["checks"].as_array().unwrap().len(), 2);
        assert_eq!(transaction["checks"][0]["name"], "power");
        assert_eq!(transaction["checks"][1]["name"], "native_plan");
    }

    #[test]
    fn native_failure_hook_persists_support_safe_failure_state() {
        let directory = tempfile::tempdir().expect("temporary transaction directory");
        crate::installer_transaction::allow_test_transaction_base(directory.path());
        let mut request = request(false);
        request.transaction_path = directory
            .path()
            .join("transaction.json")
            .to_string_lossy()
            .into_owned();
        let executor = NativePhaseExecutor::from_request(request)
            .expect("typed native install request should validate");
        executor.record_failed(Phase::Storage, "native failure secret-free");
        let transaction = std::fs::read_to_string(directory.path().join("transaction.json"))
            .expect("native failure transaction should exist");
        assert!(transaction.contains("native failure secret-free"));
        assert!(!transaction.contains("password_hash"));
        assert!(!transaction.contains("mok_password"));
    }

    #[test]
    fn wipe_storage_is_owned_by_bootc_and_resize_has_a_native_path() {
        let executor = NativePhaseExecutor::from_request(request(false))
            .expect("typed native install request should validate");
        let cancellation = CancellationToken::default();
        assert_eq!(
            executor.execute_phase_typed(Phase::Storage, &cancellation),
            Ok(())
        );
        let mut resize = request(false);
        resize.storage.install_mode = "resize_ntfs".into();
        resize.storage.resize_partition = "sda2".into();
        resize.storage.resize_gib = 40;
        let executor =
            NativePhaseExecutor::from_request(resize).expect("resize plan should validate");
        assert!(matches!(
            executor.execute_phase_typed(Phase::Storage, &cancellation),
            Err(NativePhaseError::Execution {
                phase: Phase::Storage,
                ..
            })
        ));
    }

    #[test]
    fn cancellation_is_reported_before_any_phase_operation() {
        let executor = NativePhaseExecutor::from_request(request(false))
            .expect("typed native install request should validate");
        let cancellation = CancellationToken::default();
        cancellation.cancel();
        assert_eq!(
            executor.execute_phase_typed(Phase::Prepare, &cancellation),
            Err(NativePhaseError::Cancelled {
                phase: Phase::Prepare,
            })
        );
    }
}
