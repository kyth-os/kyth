//! Port of `kyth_shared.system.probe`'s READ path — `kyth-probe.service`
//! (or an interactive Hub session) writes the on-disk cache this reads;
//! this module never writes it and never triggers a fresh probe. See
//! `probe.py`'s own module docstring for the full picture — this only
//! ports `read_section` and what it needs, not the collector/write side.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::Value;

/// Same table as `probe.py`'s `DISK_TTL` — how many seconds old a cached
/// section may be before `read_section` refuses to return it. Keep this in
/// sync with `probe.py`'s copy by hand; that file is still the source of
/// truth for what `kyth-probe.service` actually populates.
pub fn disk_ttl() -> HashMap<&'static str, f64> {
    HashMap::from([
        ("bootc-status-data", 90.0),
        ("bootc-status-text", 90.0),
        ("bootc-branch", 90.0),
        ("kernel-flavor", 600.0),
        ("flatpak-apps", 180.0),
        ("flatpak-updates", 180.0),
        ("nvidia-detect", 300.0),
        ("controllers-detect", 120.0),
        ("hardware-probes", 30.0),
        ("ntfs-drives", 30.0),
        ("secureboot-state", 300.0),
        ("hardware-summary", 30.0),
        ("network-summary", 60.0),
        ("audit-cache", 30.0),
        ("firmware-cache", 300.0),
    ])
}

fn user_runtime_cache_path() -> PathBuf {
    if let Ok(runtime) = std::env::var("XDG_RUNTIME_DIR") {
        return PathBuf::from(runtime).join("kyth").join("probe-cache.json");
    }
    let uid = rustix::process::getuid().as_raw();
    PathBuf::from(format!("/run/user/{uid}")).join("kyth").join("probe-cache.json")
}

fn user_home_cache_path() -> PathBuf {
    if let Ok(xdg) = std::env::var("XDG_CACHE_HOME") {
        return PathBuf::from(xdg).join("kyth").join("probe-cache.json");
    }
    let home = std::env::var("HOME").unwrap_or_default();
    PathBuf::from(home).join(".cache").join("kyth").join("probe-cache.json")
}

fn system_cache_path() -> PathBuf {
    PathBuf::from("/var/cache/kyth/probe-cache.json")
}

/// Same precedence as `probe.py`'s `cache_read_paths(system=False)` — this
/// crate only ever runs as the logged-in desktop user, never root, so the
/// `system=True` branch isn't ported.
pub fn cache_read_paths() -> Vec<PathBuf> {
    vec![user_runtime_cache_path(), user_home_cache_path(), system_cache_path()]
}

fn load_cache_file(path: &Path) -> Option<Value> {
    let raw = std::fs::read_to_string(path).ok()?;
    let data: Value = serde_json::from_str(&raw).ok()?;
    if !data.is_object() {
        return None;
    }
    data.get("sections")?.as_object()?;
    Some(data)
}

fn now_unix() -> f64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs_f64()).unwrap_or(0.0)
}

/// Port of `probe.py`'s `read_section(key, max_age=None, paths=None)` —
/// reads whatever `kyth-probe.service` (or a prior Hub session) already
/// cached for `key`, picking the freshest entry within its TTL across the
/// candidate paths. `paths` overrides `cache_read_paths()`, same as the
/// Python original's optional param — tests use this instead of mutating
/// process-global env vars.
pub fn read_section_in(key: &str, paths: &[PathBuf]) -> Option<Value> {
    let ttl = *disk_ttl().get(key)?;
    let now = now_unix();
    let mut best: Option<(f64, Value)> = None;
    for path in paths {
        let Some(doc) = load_cache_file(path) else { continue };
        let Some(entry) = doc.get("sections").and_then(|s| s.get(key)) else { continue };
        let Some(entry_obj) = entry.as_object() else { continue };
        let Some(ts) = entry_obj.get("ts").and_then(Value::as_f64) else { continue };
        let Some(data) = entry_obj.get("data") else { continue };
        let age = now - ts;
        if age < 0.0 || age > ttl {
            continue;
        }
        if best.as_ref().map(|(best_ts, _)| ts > *best_ts).unwrap_or(true) {
            best = Some((ts, data.clone()));
        }
    }
    best.map(|(_, data)| data)
}

/// `read_section_in` against the real `cache_read_paths()` — what every
/// non-test caller wants.
pub fn read_section(key: &str) -> Option<Value> {
    read_section_in(key, &cache_read_paths())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::fs;

    #[test]
    fn missing_cache_returns_none() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("probe-cache.json");
        assert_eq!(read_section_in("bootc-branch", &[path]), None);
    }

    #[test]
    fn unknown_key_returns_none() {
        assert_eq!(read_section_in("not-a-real-key", &[]), None);
    }

    #[test]
    fn reads_a_fresh_cache_entry() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("probe-cache.json");
        let now = now_unix();
        let doc = json!({
            "version": 2, "generated_at": now,
            "sections": { "bootc-branch": { "ts": now, "data": "testing" } },
        });
        fs::write(&path, serde_json::to_string(&doc).unwrap()).unwrap();
        assert_eq!(read_section_in("bootc-branch", &[path]), Some(json!("testing")));
    }

    #[test]
    fn stale_entry_past_its_ttl_is_ignored() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("probe-cache.json");
        // bootc-branch's TTL is 90s.
        let old = now_unix() - 200.0;
        let doc = json!({
            "version": 2, "generated_at": old,
            "sections": { "bootc-branch": { "ts": old, "data": "testing" } },
        });
        fs::write(&path, serde_json::to_string(&doc).unwrap()).unwrap();
        assert_eq!(read_section_in("bootc-branch", &[path]), None);
    }

    #[test]
    fn picks_the_freshest_entry_across_candidate_paths() {
        let dir = tempfile::tempdir().unwrap();
        let now = now_unix();
        let older_path = dir.path().join("older.json");
        let newer_path = dir.path().join("newer.json");
        fs::write(
            &older_path,
            serde_json::to_string(&json!({
                "version": 2, "sections": { "bootc-branch": { "ts": now - 50.0, "data": "stale-value" } },
            }))
            .unwrap(),
        )
        .unwrap();
        fs::write(
            &newer_path,
            serde_json::to_string(&json!({
                "version": 2, "sections": { "bootc-branch": { "ts": now, "data": "fresh-value" } },
            }))
            .unwrap(),
        )
        .unwrap();
        // Deliberately listed newest-last, to prove this picks the freshest
        // entry rather than the first match.
        assert_eq!(
            read_section_in("bootc-branch", &[older_path, newer_path]),
            Some(json!("fresh-value"))
        );
    }
}
