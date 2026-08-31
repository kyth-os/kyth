use serde::Serialize;

#[derive(Serialize)]
pub(crate) struct ProbeResponse {
    pub(crate) key: String,
    pub(crate) data: Option<serde_json::Value>,
    pub(crate) error: Option<String>,
}

/// Read a disk-backed probe section. This remains read-only and does not
/// trigger a fresh system probe.
#[tauri::command]
pub(crate) fn probe_backend(section: String) -> ProbeResponse {
    let data = kyth_shared::system::probe::read_section(&section);
    ProbeResponse { key: section, data, error: None }
}

#[derive(Serialize)]
pub(crate) struct HardwareResponse {
    pub(crate) gpu_line: Option<String>,
}

#[tauri::command]
pub(crate) fn hardware_snapshot() -> HardwareResponse {
    HardwareResponse { gpu_line: kyth_shared::system::gpu::lspci_gpu_lines().into_iter().next() }
}

#[derive(Serialize)]
pub(crate) struct StorageResponse {
    pub(crate) free_bytes: Option<u64>,
    pub(crate) total_bytes: Option<u64>,
}

#[tauri::command]
pub(crate) fn storage_snapshot() -> StorageResponse {
    match kyth_shared::system::storage::primary_disk_usage() {
        Some(usage) => StorageResponse { free_bytes: Some(usage.free_bytes), total_bytes: Some(usage.total_bytes) },
        None => StorageResponse { free_bytes: None, total_bytes: None },
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
pub(crate) fn boot_runtime_checks() -> Vec<BootRuntimeCheckResponse> {
    kyth_shared::system::boot_runtime::boot_runtime_checks()
        .into_iter()
        .map(|check| BootRuntimeCheckResponse { name: check.name, passed: check.passed, detail: check.detail })
        .collect()
}

#[derive(Serialize)]
pub(crate) struct RecoveryStatusResponse {
    pub(crate) has_staged: bool,
    pub(crate) has_rollback: bool,
    pub(crate) quarantined_digest: String,
    pub(crate) quarantine_detail: String,
    pub(crate) watcher_staged: bool,
    pub(crate) clear_quarantine_cmd: String,
    pub(crate) banner: String,
}

#[tauri::command]
pub(crate) fn recovery_status() -> RecoveryStatusResponse {
    let status = kyth_shared::system::recovery_status::get_recovery_status();
    let banner = kyth_shared::system::recovery_status::recovery_banner(&status);
    RecoveryStatusResponse {
        has_staged: status.has_staged,
        has_rollback: status.has_rollback,
        quarantined_digest: status.quarantined_digest,
        quarantine_detail: status.quarantine_detail,
        watcher_staged: status.watcher_staged,
        clear_quarantine_cmd: status.clear_quarantine_cmd,
        banner,
    }
}
