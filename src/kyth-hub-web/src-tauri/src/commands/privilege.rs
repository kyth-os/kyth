use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;
use std::sync::{Mutex, OnceLock};

use serde_json::{json, Value};

static JOBS: OnceLock<Mutex<HashMap<String, (String, String)>>> = OnceLock::new();

fn jobs() -> &'static Mutex<HashMap<String, (String, String)>> {
    JOBS.get_or_init(|| Mutex::new(HashMap::new()))
}

/// Validate and construct the only requests the root-owned service accepts.
/// The BitLocker key is copied into the request only after validation and is
/// never included in an error or job status message.
fn validated_request(operation: &str, payload: &Value) -> Result<Value, String> {
    match operation {
        "flatpak_uninstall" => {
            let app_id = payload.get("app_id").and_then(Value::as_str).ok_or_else(|| "Flatpak application id is required".to_string())?;
            validate_flatpak_id(app_id)?;
            Ok(json!({ "operation": "flatpak_uninstall", "app_id": app_id }))
        }
        "firmware_update" | "nvidia_install" | "windows_verify" | "secureboot_enroll" => {
            Ok(json!({ "operation": operation }))
        }
        "kernel_switch" => {
            let flavor = payload.get("flavor").and_then(Value::as_str).ok_or_else(|| "kernel flavor is required".to_string())?;
            if !matches!(flavor, "fedora" | "cachy") {
                return Err("kernel flavor must be fedora or cachy".to_string());
            }
            Ok(json!({ "operation": "kernel_switch", "flavor": flavor }))
        }
        "bitlocker_unlock" => {
            let device = payload.get("device").and_then(Value::as_str).ok_or_else(|| "block device is required".to_string())?;
            let key = payload.get("key").and_then(Value::as_str).ok_or_else(|| "BitLocker key is required".to_string())?;
            if !valid_block_device(device) {
                return Err("invalid block device".to_string());
            }
            if !(8..=128).contains(&key.len()) || key.contains(['\n', '\r']) {
                return Err("invalid BitLocker key".to_string());
            }
            Ok(json!({ "operation": "bitlocker_unlock", "device": device, "key": key }))
        }
        _ => Err("privileged operation is not allowlisted".to_string()),
    }
}

pub(crate) fn validate_flatpak_id(value: &str) -> Result<(), String> {
    if value.len() > 200 {
        return Err("invalid Flatpak application id".to_string());
    }
    let parts: Vec<&str> = value.split(['.', '-']).collect();
    if parts.len() < 2
        || !parts[0].bytes().all(|byte| byte.is_ascii_alphanumeric())
        || parts[1..].iter().any(|part| part.is_empty() || !part.bytes().all(|byte| byte.is_ascii_alphanumeric() || byte == b'_'))
    {
        return Err("invalid Flatpak application id".to_string());
    }
    Ok(())
}

fn valid_block_device(value: &str) -> bool {
    let Some(name) = value.strip_prefix("/dev/") else { return false };
    if name.is_empty() || name.len() > 64 || name.contains('/') || !name.is_ascii() {
        return false;
    }
    if let Some(rest) = name.strip_prefix("sd").or_else(|| name.strip_prefix("vd")) {
        return rest.len() >= 1 && rest.as_bytes()[0].is_ascii_lowercase() && rest[1..].bytes().all(|byte| byte.is_ascii_digit());
    }
    if let Some(rest) = name.strip_prefix("nvme") {
        let Some((controller, namespace)) = rest.split_once('n') else { return false };
        let (namespace, partition) = namespace.split_once('p').map_or((namespace, ""), |(n, p)| (n, p));
        return !controller.is_empty() && controller.bytes().all(|byte| byte.is_ascii_digit())
            && !namespace.is_empty() && namespace.bytes().all(|byte| byte.is_ascii_digit())
            && partition.bytes().all(|byte| byte.is_ascii_digit());
    }
    if let Some(rest) = name.strip_prefix("mmcblk") {
        let Some((device, partition)) = rest.split_once('p') else { return false };
        return !device.is_empty() && device.bytes().all(|byte| byte.is_ascii_digit())
            && !partition.is_empty() && partition.bytes().all(|byte| byte.is_ascii_digit());
    }
    false
}

#[tauri::command]
pub(crate) fn privileged_action(operation: String, payload: Value) -> Result<String, String> {
    let request = validated_request(&operation, &payload)?;
    let job = format!("privileged-{}", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_nanos());
    jobs().lock().map_err(|_| "privileged job store is unavailable".to_string())?.insert(job.clone(), ("running".into(), format!("Running {operation}…")));
    let job_for_thread = job.clone();
    std::thread::spawn(move || {
        let result = send_request(request);
        let (state, detail) = match result {
            Ok(detail) => ("complete", detail),
            Err(detail) => ("failed", detail),
        };
        if let Ok(mut store) = jobs().lock() {
            store.insert(job_for_thread, (state.into(), detail));
        }
    });
    Ok(job)
}

pub(crate) fn send_request(request: Value) -> Result<String, String> {
    let mut stream = UnixStream::connect("/run/kyth/privileged.sock").map_err(|_| "privileged service is unavailable".to_string())?;
    stream.set_read_timeout(Some(std::time::Duration::from_secs(910))).map_err(|error| format!("could not configure privileged service timeout: {error}"))?;
    stream.write_all(format!("{request}\n").as_bytes()).map_err(|error| format!("could not contact privileged service: {error}"))?;
    let mut response = String::new();
    BufReader::new(stream).read_line(&mut response).map_err(|error| format!("could not read privileged service: {error}"))?;
    let value: Value = serde_json::from_str(&response).map_err(|error| format!("invalid privileged service response: {error}"))?;
    if value.get("ok").and_then(Value::as_bool).unwrap_or(false) {
        Ok(value.get("detail").and_then(Value::as_str).unwrap_or("Operation complete.").to_string())
    } else {
        Err(value.get("detail").and_then(Value::as_str).unwrap_or("privileged operation failed").to_string())
    }
}

#[allow(dead_code)]
pub(crate) fn bitlocker_request(device: &str, key: &str) -> Result<Value, String> {
    validated_request("bitlocker_unlock", &json!({ "device": device, "key": key }))
}

pub(crate) fn flatpak_uninstall(app_id: &str) -> Result<String, String> {
    let request = validated_request("flatpak_uninstall", &json!({ "app_id": app_id }))?;
    send_request(request)
}

#[tauri::command]
pub(crate) fn privileged_action_status(job: String) -> crate::InstallStatus {
    let (state, detail) = jobs().lock().ok().and_then(|store| store.get(&job).cloned()).unwrap_or(("unknown".into(), "Privileged job not found.".into()));
    crate::InstallStatus { id: job, state, detail }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::validated_request;

    #[test]
    fn only_allowlisted_operations_are_constructed() {
        assert!(validated_request("not-allowed", &json!({})).is_err());
        assert_eq!(validated_request("kernel_switch", &json!({ "flavor": "cachy" })).unwrap()["flavor"], "cachy");
        assert!(validated_request("flatpak_uninstall", &json!({ "app_id": "org.example.App" })).is_ok());
        assert!(validated_request("flatpak_uninstall", &json!({ "app_id": "org.example-App" })).is_ok());
        assert!(validated_request("flatpak_uninstall", &json!({ "app_id": "_org.example" })).is_err());
    }

    #[test]
    fn bitlocker_validation_rejects_bad_devices_and_keys_without_echoing_secret() {
        let error = validated_request("bitlocker_unlock", &json!({ "device": "/tmp/disk", "key": "secret-key" })).unwrap_err();
        assert_eq!(error, "invalid block device");
        let error = validated_request("bitlocker_unlock", &json!({ "device": "/dev/sda1", "key": "short" })).unwrap_err();
        assert_eq!(error, "invalid BitLocker key");
        assert!(!error.contains("short"));
    }
}
