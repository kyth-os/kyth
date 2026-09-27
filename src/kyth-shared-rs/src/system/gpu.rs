//! Port of `kyth_shared.system.gpu`'s `lspci_gpu_lines()` — one
//! `lspci -nn` call, filtered to display-controller lines. Same plain
//! substring match as the Python original (`"vga"`/`"3d"`/`"display"`
//! anywhere in the lowercased line, not word-boundary — a line like
//! "Non-VGA unclassified device" does match on `"vga"` in both this and
//! the Python original; ported as-is, not "fixed", since changing that
//! behavior isn't this port's job).

use std::time::Duration;

pub fn lspci_gpu_lines() -> Vec<String> {
    let argv = ["lspci", "-nn"]
        .into_iter()
        .map(str::to_string)
        .collect::<Vec<_>>();
    let Ok(output) = super::process::run_bounded(&argv, Duration::from_secs(5)) else {
        return Vec::new();
    };
    if !output.status.success() {
        return Vec::new();
    }
    String::from_utf8_lossy(&output.stdout)
        .lines()
        .filter(|line| {
            let lower = line.to_lowercase();
            lower.contains("vga") || lower.contains("3d") || lower.contains("display")
        })
        .map(str::to_string)
        .collect()
}

/// Serializable form of the GPU snapshot for the `hardware-snapshot` probe
/// section: the Hub reads the cached section first (TTL 600 s) and only
/// shells out to `lspci` on a cache miss, instead of spawning it on every
/// Hardware page open.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct HardwareSnapshot {
    pub gpu_lines: Vec<String>,
}

pub fn hardware_snapshot_section() -> HardwareSnapshot {
    HardwareSnapshot {
        gpu_lines: lspci_gpu_lines(),
    }
}

/// First GPU line, preferring the cached `hardware-snapshot` probe section
/// over a live `lspci` call.
pub fn cached_gpu_line() -> Option<String> {
    if let Some(cached) = crate::system::probe::read_system_section("hardware-snapshot")
        .or_else(|| crate::system::probe::read_section("hardware-snapshot"))
    {
        if let Ok(snapshot) = serde_json::from_value::<HardwareSnapshot>(cached) {
            if let Some(line) = snapshot.gpu_lines.into_iter().next() {
                return Some(line);
            }
        }
    }
    lspci_gpu_lines().into_iter().next()
}

#[cfg(test)]
mod tests {
    use super::*;

    // No lspci-availability assertion here — whether it's installed is a
    // property of the machine running the tests, not this function.
    // Correctness of the filter itself is exercised at the bridge-command
    // layer (see src-tauri's tests) where a fake `lspci` on PATH is cheap
    // to set up; this crate has no subprocess-injection seam of its own.
    #[test]
    fn does_not_panic_when_lspci_is_missing() {
        let _ = lspci_gpu_lines();
    }
}
