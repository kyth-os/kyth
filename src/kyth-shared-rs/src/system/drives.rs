//! Port of `kyth_shared.system.drives` — NTFS/sanitize + mount helpers.

use std::path::Path;

// Simplified allow-list without regex crate: manual prefix checks
fn sanitize_dev_path(raw: &str) -> Option<String> {
    if raw.is_empty() { return None; }
    let c = Path::new(raw).canonicalize().ok()?.to_string_lossy().to_string();
    if c.starts_with("/dev/sd") || c.starts_with("/dev/nvme") || c.starts_with("/dev/vd") || c.starts_with("/dev/mmcblk") {
        // Basic check: must match /dev/(sd[a-z][0-9]* etc.)
        if c.starts_with("/dev/") && !c.contains("..") && !c.contains(' ') { return Some(c); }
    }
    None
}

fn sanitize_mount(raw: &str) -> Option<String> {
    const PREFIX: &str = "/var/mnt/ntfs_";
    if raw.is_empty() || !raw.starts_with(PREFIX) { return None; }
    let c = Path::new(raw).canonicalize().ok()?.to_string_lossy().to_string();
    if c.starts_with(PREFIX) || c == "/var/mnt" { return Some(c); }
    None
}

pub fn get_ntfs_devices() -> Vec<serde_json::Value> {
    use std::process::Command;
    let out = Command::new("lsblk").args(["-J","-o","NAME,FSTYPE,LABEL,UUID,MOUNTPOINT"]).output();
    if let Ok(o) = out {
        if o.status.success() {
            if let Ok(s) = String::from_utf8(o.stdout) {
                if let Ok(v) = serde_json::from_str::<serde_json::Value>(&s) {
                    // Simplified: return blockdevices array
                    if let Some(arr) = v.get("blockdevices").and_then(|a| a.as_array()) {
                        return arr.iter().cloned().collect();
                    }
                }
            }
        }
    }
    Vec::new()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn sanitize_none() {
        assert!(sanitize_dev_path("").is_none());
        assert!(sanitize_dev_path("../../etc/passwd").is_none());
    }
}
