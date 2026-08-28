//! Port of kyth_shared.system.snapshot — snapper/btrfs list stub (read-only).
//! Full port is snapper --json + btrfs subvolume list; this first slice
//! ports the probe-cached snapshot count check used by Repair timeline.
use std::process::Command;
pub fn snapshot_count() -> usize {
    // Mirrors snapshot.py's `snapper list --json` count fallback
    let out = Command::new("snapper").args(["list","--json"]).output();
    if let Ok(o) = out { if o.status.success() { if let Ok(s)=String::from_utf8(o.stdout) { if let Ok(v)=serde_json::from_str::<serde_json::Value>(&s){ if let Some(arr)=v.get("snapshots").and_then(|a| a.as_array()){ return arr.len(); } } } } }
    0
}
#[cfg(test)] mod tests { use super::*; #[test] fn count_is_usize(){ let _=snapshot_count(); } }
