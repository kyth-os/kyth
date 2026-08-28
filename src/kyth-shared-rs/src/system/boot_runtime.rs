//! Port of `kyth_shared.system.boot_runtime` — runtime boot assertions.

use std::path::Path;
use std::process::Command;

#[derive(Debug, Clone)]
pub struct RuntimeCheck { pub name: String, pub passed: bool, pub detail: String }

pub fn boot_runtime_checks() -> Vec<RuntimeCheck> {
    let mut out = Vec::new();
    // systemd booted?
    let systemd = Path::new("/run/systemd/system").is_dir();
    out.push(RuntimeCheck { name: "systemd".to_string(), passed: systemd, detail: if systemd {"systemd running".to_string()} else {"not booted with systemd".to_string()} });
    // graphical target
    let target = Command::new("systemctl").arg("get-default").output().ok().map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string()).unwrap_or_default();
    out.push(RuntimeCheck { name: "graphical.target".to_string(), passed: target=="graphical.target", detail: target });
    // DRM device
    let drm = Path::new("/dev/dri").exists();
    out.push(RuntimeCheck { name: "drm".to_string(), passed: drm, detail: if drm {"DRM device exists".to_string()} else {"no /dev/dri".to_string()} });
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn checks() { let _ = boot_runtime_checks(); }
}
