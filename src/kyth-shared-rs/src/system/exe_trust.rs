//! Trust-once store for double-clicked Windows executables.
//!
//! The first double-click opens the Hub dialog; "always run this file
//! directly" records the file's full SHA-256 here. Later double-clicks with
//! a matching hash launch straight into the recorded runner with no UI.
//! Trust is keyed by content hash, never by path: a modified file has a
//! different hash and falls back to the dialog.

use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// Runners the trust store may record.
pub const RUNNER_BOTTLES: &str = "bottles";
pub const RUNNER_UMU: &str = "umu";

fn trust_path(home: &Path) -> PathBuf {
    home.join(".config/kyth/exe-trust.json")
}

fn config_home() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/"))
}

/// Full SHA-256 of a file, streamed so multi-GB installers never load
/// fully into memory.
pub fn full_sha256(path: &Path) -> Option<String> {
    use std::io::Read;
    let mut file = std::fs::File::open(path).ok()?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 65536];
    loop {
        match file.read(&mut buf) {
            Ok(0) => break,
            Ok(n) => hasher.update(&buf[..n]),
            Err(_) => return None,
        }
    }
    Some(format!("{:x}", hasher.finalize()))
}

fn load_trust(home: &Path) -> BTreeMap<String, Value> {
    std::fs::read_to_string(trust_path(home))
        .ok()
        .and_then(|text| serde_json::from_str::<Value>(&text).ok())
        .and_then(|value| serde_json::from_value::<BTreeMap<String, Value>>(value).ok())
        .unwrap_or_default()
}

/// Runner recorded for this exact file content, if the user trusted it.
pub fn trusted_runner(home: &Path, sha256: &str) -> Option<String> {
    load_trust(home)
        .get(sha256)
        .and_then(|entry| entry.get("runner"))
        .and_then(Value::as_str)
        .filter(|runner| *runner == RUNNER_BOTTLES || *runner == RUNNER_UMU)
        .map(str::to_string)
}

/// Record trust for exact file content. Atomic write: a half-written store
/// must never grant trust.
pub fn trust_file(home: &Path, sha256: &str, name: &str, runner: &str) -> Result<(), String> {
    if runner != RUNNER_BOTTLES && runner != RUNNER_UMU {
        return Err("unknown runner".to_string());
    }
    if sha256.len() != 64 || !sha256.chars().all(|c| c.is_ascii_hexdigit()) {
        return Err("trust requires a full SHA-256 hex digest".to_string());
    }
    let mut store = load_trust(home);
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    store.insert(
        sha256.to_ascii_lowercase(),
        serde_json::json!({"name": name, "runner": runner, "at": now}),
    );
    let path = trust_path(home);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("could not create trust store: {error}"))?;
    }
    let temporary = path.with_extension("json.tmp");
    std::fs::write(
        &temporary,
        serde_json::to_string(&store).unwrap_or_default(),
    )
    .map_err(|error| format!("could not write trust store: {error}"))?;
    std::fs::rename(&temporary, &path)
        .map_err(|error| format!("could not write trust store: {error}"))?;
    Ok(())
}

/// Drop trust for one hash. Missing entries are a no-op success.
pub fn untrust_file(home: &Path, sha256: &str) -> Result<(), String> {
    let mut store = load_trust(home);
    if store.remove(&sha256.to_ascii_lowercase()).is_none() {
        return Ok(());
    }
    let path = trust_path(home);
    let temporary = path.with_extension("json.tmp");
    std::fs::write(
        &temporary,
        serde_json::to_string(&store).unwrap_or_default(),
    )
    .map_err(|error| format!("could not write trust store: {error}"))?;
    std::fs::rename(&temporary, &path)
        .map_err(|error| format!("could not write trust store: {error}"))?;
    Ok(())
}

pub fn trusted_runner_for_current_user(sha256: &str) -> Option<String> {
    trusted_runner(&config_home(), sha256)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn trust_round_trips_and_rejects_short_hashes() {
        let home = tempdir().unwrap();
        let digest = "ab".repeat(32);
        assert_eq!(trusted_runner(home.path(), &digest), None);
        trust_file(home.path(), &digest, "setup.exe", RUNNER_BOTTLES).unwrap();
        assert_eq!(
            trusted_runner(home.path(), &digest),
            Some(RUNNER_BOTTLES.to_string())
        );
        // Unknown runners and prefix hashes never grant trust.
        assert!(trust_file(home.path(), &digest, "setup.exe", "wine").is_err());
        assert!(trust_file(home.path(), "abcdef", "setup.exe", RUNNER_BOTTLES).is_err());
        untrust_file(home.path(), &digest).unwrap();
        assert_eq!(trusted_runner(home.path(), &digest), None);
    }

    #[test]
    fn full_hash_streams_large_files() {
        let home = tempdir().unwrap();
        let path = home.path().join("big.exe");
        let content = vec![0x58u8; 3 << 20];
        std::fs::write(&path, &content).unwrap();
        let mut expected = Sha256::new();
        expected.update(&content);
        assert_eq!(
            full_sha256(&path),
            Some(format!("{:x}", expected.finalize()))
        );
    }
}
