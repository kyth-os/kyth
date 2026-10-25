use serde::Serialize;

#[derive(Serialize)]
pub(crate) struct ProbeResponse {
    pub(crate) key: String,
    pub(crate) data: Option<serde_json::Value>,
    pub(crate) error: Option<String>,
}

/// Read a disk-backed probe section. Boot status and branch have a bounded
/// native fallback because the Updates page must remain useful when the
/// optional probe service has not populated its cache yet.
#[tauri::command]
pub(crate) async fn probe_backend(section: String) -> ProbeResponse {
    // The section name used to be echoed back verbatim in `key` and the
    // error message. Probe sections are `[a-z0-9_-]` names; anything else
    // fails closed without reflecting the input.
    if section.is_empty()
        || section.len() > 128
        || !section
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
    {
        return ProbeResponse {
            key: String::new(),
            data: None,
            error: Some("Invalid probe section.".to_string()),
        };
    }
    let key = section.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let data = match section.as_str() {
            "bootc-status-data" => kyth_shared::system::probe::read_section(&section)
                .or_else(kyth_shared::system::bootc_query::fetch_status_data),
            "bootc-branch" => kyth_shared::system::probe::read_section(&section).or_else(|| {
                kyth_shared::system::bootc::current_branch().map(serde_json::Value::String)
            }),
            _ => kyth_shared::system::probe::read_section(&section),
        };
        // A miss used to read as loaded-empty (`data: None, error: None`).
        // Signal it so callers can tell "no data yet" from "empty data".
        let error = if data.is_none() {
            Some(format!("No probe data for section '{section}' yet."))
        } else {
            None
        };
        ProbeResponse {
            key: section,
            data,
            error,
        }
    })
    .await
    .unwrap_or_else(|_| ProbeResponse {
        key,
        data: None,
        error: Some("Could not read probe data.".to_string()),
    })
}

#[derive(Serialize)]
pub(crate) struct HardwareResponse {
    pub(crate) gpu_line: Option<String>,
}

#[tauri::command]
pub(crate) async fn hardware_snapshot() -> Result<HardwareResponse, String> {
    // A panicked worker used to collapse to `gpu_line: None`, the same
    // value as "no GPU found": the JoinError now surfaces as an error,
    // the probe_backend discipline. (A failed lspci inside the worker
    // still reads as no GPU — the shared probe returns an empty list
    // for both, and cannot tell them apart.)
    tauri::async_runtime::spawn_blocking(|| HardwareResponse {
        gpu_line: kyth_shared::system::gpu::lspci_gpu_lines()
            .into_iter()
            .next(),
    })
    .await
    .map_err(|error| format!("Could not read the graphics hardware: {error}"))
}

#[derive(Serialize)]
pub(crate) struct StorageResponse {
    pub(crate) free_bytes: Option<u64>,
    pub(crate) total_bytes: Option<u64>,
}

#[tauri::command]
pub(crate) fn storage_snapshot() -> StorageResponse {
    match kyth_shared::system::storage::primary_disk_usage() {
        Some(usage) => StorageResponse {
            free_bytes: Some(usage.free_bytes),
            total_bytes: Some(usage.total_bytes),
        },
        None => StorageResponse {
            free_bytes: None,
            total_bytes: None,
        },
    }
}

#[tauri::command]
pub(crate) fn current_user_name() -> String {
    kyth_shared::system::account::current_user_display_name()
}

#[derive(Serialize)]
pub(crate) struct BootRuntimeCheckResponse {
    pub(crate) name: String,
    pub(crate) passed: bool,
    pub(crate) detail: String,
}

#[tauri::command]
pub(crate) async fn boot_runtime_checks() -> Result<Vec<BootRuntimeCheckResponse>, String> {
    // A panicked worker used to return an empty list, which Diagnostics
    // renders like a clean sweep; the JoinError now surfaces as an
    // error instead.
    tauri::async_runtime::spawn_blocking(|| {
        kyth_shared::system::boot_runtime::boot_runtime_checks()
            .into_iter()
            .map(|check| BootRuntimeCheckResponse {
                name: check.name,
                passed: check.passed,
                detail: check.detail,
            })
            .collect()
    })
    .await
    .map_err(|error| format!("Could not run the boot runtime checks: {error}"))
}

#[derive(Serialize)]
pub(crate) struct RecoveryStatusResponse {
    pub(crate) has_staged: bool,
    pub(crate) has_rollback: bool,
    pub(crate) quarantined_digest: String,
    pub(crate) quarantine_detail: String,
    pub(crate) watcher_staged: bool,
    pub(crate) clear_quarantine_cmd: String,
    pub(crate) last_rollback_error: String,
    pub(crate) banner: String,
}

#[tauri::command]
pub(crate) async fn recovery_status() -> RecoveryStatusResponse {
    // get_recovery_status shells out to bootc with multi-second
    // per-attempt bounds and the Dashboard polls this: it belongs on
    // the blocking pool, not a command worker.
    tauri::async_runtime::spawn_blocking(|| {
        let status = kyth_shared::system::recovery_status::get_recovery_status();
        let banner = kyth_shared::system::recovery_status::recovery_banner(&status);
        RecoveryStatusResponse {
            has_staged: status.has_staged,
            has_rollback: status.has_rollback,
            quarantined_digest: status.quarantined_digest,
            quarantine_detail: status.quarantine_detail,
            watcher_staged: status.watcher_staged,
            clear_quarantine_cmd: status.clear_quarantine_cmd,
            last_rollback_error: status.last_rollback_error,
            banner,
        }
    })
    .await
    .unwrap_or_else(|_| RecoveryStatusResponse {
        has_staged: false,
        has_rollback: false,
        quarantined_digest: String::new(),
        quarantine_detail: String::new(),
        watcher_staged: false,
        clear_quarantine_cmd: String::new(),
        last_rollback_error: String::new(),
        // The banner names the failure so a dead worker cannot read as
        // "nothing staged, no rollback, all clear".
        banner: "Recovery status could not be read.".to_string(),
    })
}
