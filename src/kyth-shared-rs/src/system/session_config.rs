//! User-session configuration transforms and their best-effort file writes.
//!
//! The pure `update_*` renders mirror `kyth_shared.session`; the
//! `*_file` appliers and `enable_vscode_brave_wallet_prompts` own the
//! `kyth-vscode-wallet` launcher surface. `session.py` stays as the
//! Phase 3 fixture.

use std::path::{Path, PathBuf};

/// Set VS Code's password store without preserving malformed/non-object JSON.
pub fn update_code_argv(raw: Option<&str>) -> String {
    let mut value = raw
        .and_then(|raw| serde_json::from_str::<serde_json::Value>(raw).ok())
        .filter(serde_json::Value::is_object)
        .unwrap_or_else(|| serde_json::json!({}));
    value.as_object_mut().unwrap().insert(
        "password-store".into(),
        serde_json::Value::String("kwallet5".into()),
    );
    format!(
        "{}\n",
        serde_json::to_string_pretty(&value).expect("JSON object serializes")
    )
}

/// Replace an existing Chromium/Brave password-store flag, or append one.
pub fn update_chromium_flags(raw: Option<&str>) -> String {
    let mut updated = Vec::new();
    let mut wrote = false;
    for line in raw.unwrap_or_default().lines() {
        let stripped = line.trim();
        if stripped.starts_with("--password-store=") || stripped.starts_with("password-store=") {
            if !wrote {
                updated.push("--password-store=kwallet5".to_string());
                wrote = true;
            }
        } else {
            updated.push(line.to_string());
        }
    }
    if !wrote {
        updated.push("--password-store=kwallet5".into());
    }
    format!("{}\n", updated.join("\n").trim_end())
}

/// VS Code's per-user arguments file.
pub fn code_argv_path(home: &Path) -> PathBuf {
    home.join(".config/Code/argv.json")
}

/// Every Brave/Chromium flags file the launcher rewrites, in order.
pub fn chromium_flags_paths(home: &Path) -> Vec<PathBuf> {
    [
        ".config/brave-flags.conf",
        ".config/BraveSoftware/Brave-Browser/brave-flags.conf",
        ".config/BraveSoftware/Brave-Browser/chrome-flags.conf",
        ".var/app/com.brave.Browser/config/brave-flags.conf",
        ".var/app/com.brave.Browser/config/chrome-flags.conf",
        ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/brave-flags.conf",
        ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/chrome-flags.conf",
    ]
    .iter()
    .map(|rel| home.join(rel))
    .collect()
}

/// Best-effort rewrite of VS Code's argv.json: missing parents are
/// created, a missing or unreadable file starts empty, and write
/// failures are swallowed. Merges keys into the existing object (unknown
/// user keys are preserved) and snapshots the previous file first.
pub fn write_code_argv_file(path: &Path) {
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let _ = snapshot_before_write(path);
    let existing = std::fs::read_to_string(path).ok();
    let _ = std::fs::write(path, update_code_argv(existing.as_deref()));
}

/// Best-effort rewrite of one flags file: snapshots the previous file,
/// then merges the password-store flag (other flags are preserved).
pub fn write_chromium_flags_file(path: &Path) {
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let _ = snapshot_before_write(path);
    let existing = std::fs::read_to_string(path).unwrap_or_default();
    let _ = std::fs::write(path, update_chromium_flags(Some(&existing)));
}

/// Timestamped backup of `path` next to itself (`<name>.YYYYmmdd-HHMMSS.bak`).
/// Returns the snapshot path. Missing source files are a no-op (`Ok` with the
/// would-be name); callers ignore the result on a best-effort path.
pub fn snapshot_before_write(path: &Path) -> std::io::Result<PathBuf> {
    let stamp = snapshot_stamp();
    let file_name = path
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default();
    let backup = path.with_file_name(format!("{file_name}.{stamp}.bak"));
    if path.exists() {
        std::fs::copy(path, &backup)?;
    }
    Ok(backup)
}

/// UTC `YYYYmmdd-HHMMSS` stamp for snapshot filenames. Reads
/// `/proc` clock-free via `SystemTime`; falls back to the epoch on error.
pub fn snapshot_stamp() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_secs())
        .unwrap_or(0);
    const DAYS_TO_CIVIL: fn(u64) -> (i64, u32, u32) = |days| {
        let z = days as i64 + 719_468;
        let era = z.div_euclid(146_097);
        let doe = z.rem_euclid(146_097);
        let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
        let year = yoe + era * 400;
        let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
        let mp = (5 * doy + 2) / 153;
        let day = (doy - (153 * mp + 2) / 5 + 1) as u32;
        let month = (if mp < 10 { mp + 3 } else { mp - 9 }) as u32;
        (if month <= 2 { year + 1 } else { year }, month, day)
    };
    let (year, month, day) = DAYS_TO_CIVIL(secs / 86_400);
    let rest = secs % 86_400;
    format!(
        "{year:04}{month:02}{day:02}-{:02}{:02}{:02}",
        rest / 3_600,
        rest % 3_600 / 60,
        rest % 60
    )
}

/// Restore `path` from a snapshot created by [`snapshot_before_write`].
/// `--force-restore` flows here: the snapshot wins wholesale, no merging.
pub fn restore_snapshot(path: &Path, backup: &Path) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let bytes = std::fs::read(backup)?;
    std::fs::write(path, bytes)
}

/// Minimum Plasma release a config migration is written for. Older sessions
/// keep their files untouched: migrating forward under Plasma 5 (or an
/// unparseable version string) corrupts keys the running shell still owns.
pub const MIN_PLASMA_MIGRATION_VERSION: (u64, u64) = (6, 0);

/// Parse `plasmashell --version`-style output (`"plasmashell 6.1.5"`) into
/// `(major, minor)`. Returns `None` when nothing parseable is present.
pub fn parse_plasma_version(output: &str) -> Option<(u64, u64)> {
    for token in output.split(|char: char| !(char.is_ascii_alphanumeric() || char == '.')) {
        let mut parts = token.split('.');
        if let (Some(major), Some(minor)) = (parts.next(), parts.next()) {
            if let (Ok(major), Ok(minor)) = (major.parse(), minor.parse()) {
                return Some((major, minor));
            }
        }
    }
    None
}

/// Gate for Plasma config migrations: only run when the running Plasma is at
/// least [`MIN_PLASMA_MIGRATION_VERSION`]. Unknown versions fail closed.
pub fn should_run_plasma_migration(version_output: &str) -> bool {
    parse_plasma_version(version_output)
        .is_some_and(|version| version >= MIN_PLASMA_MIGRATION_VERSION)
}

/// Enable KWallet integration for VS Code and Brave under home.
pub fn enable_vscode_brave_wallet_prompts(home: &Path) {
    write_code_argv_file(&code_argv_path(home));
    for flags_path in chromium_flags_paths(home) {
        write_chromium_flags_file(&flags_path);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn updates_code_json_and_recovers_from_malformed_input() {
        assert!(update_code_argv(Some(r#"{"theme":"dark"}"#))
            .contains("\"password-store\": \"kwallet5\""));
        assert_eq!(
            update_code_argv(Some("bad json")),
            "{\n  \"password-store\": \"kwallet5\"\n}\n"
        );
    }

    #[test]
    fn de_duplicates_chromium_password_store_flags() {
        let output =
            update_chromium_flags(Some("--foo\n--password-store=basic\npassword-store=old\n"));
        assert_eq!(output.matches("password-store=").count(), 1);
        assert!(output.contains("--password-store=kwallet5"));
    }

    #[test]
    fn wallet_paths_cover_code_and_all_brave_variants() {
        let home = Path::new("/home/demo");
        assert_eq!(
            code_argv_path(home),
            PathBuf::from("/home/demo/.config/Code/argv.json")
        );
        let paths = chromium_flags_paths(home);
        assert_eq!(paths.len(), 7);
        assert!(paths.iter().all(|path| path.starts_with(home)));
    }

    #[test]
    fn enable_writes_all_files_and_is_idempotent() {
        let home = tempfile::tempdir().unwrap();
        enable_vscode_brave_wallet_prompts(home.path());
        enable_vscode_brave_wallet_prompts(home.path());
        let argv = std::fs::read_to_string(home.path().join(".config/Code/argv.json")).unwrap();
        assert!(argv.contains("kwallet5"));
        for path in chromium_flags_paths(home.path()) {
            let content = std::fs::read_to_string(&path).unwrap();
            assert_eq!(content.matches("password-store=").count(), 1, "{path:?}");
            assert!(content.contains("--password-store=kwallet5"));
        }
    }

    #[test]
    fn snapshots_are_timestamped_and_restore_force_wins() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("argv.json");
        std::fs::write(&path, r#"{"theme":"dark"}"#).unwrap();
        let backup = snapshot_before_write(&path).unwrap();
        let name = backup.file_name().unwrap().to_string_lossy().into_owned();
        assert!(name.starts_with("argv.json."));
        assert!(name.ends_with(".bak"));
        assert_eq!(
            std::fs::read_to_string(&backup).unwrap(),
            r#"{"theme":"dark"}"#
        );
        // Merge path preserves the user's theme key while adding the store.
        write_code_argv_file(&path);
        let merged = std::fs::read_to_string(&path).unwrap();
        assert!(merged.contains("dark"));
        assert!(merged.contains("kwallet5"));
        // Force restore brings back the exact pre-write bytes.
        std::fs::write(&path, "clobbered").unwrap();
        restore_snapshot(&path, &backup).unwrap();
        assert_eq!(
            std::fs::read_to_string(&path).unwrap(),
            r#"{"theme":"dark"}"#
        );
    }

    #[test]
    fn plasma_migration_gate_rejects_old_and_unknown_versions() {
        assert!(should_run_plasma_migration("plasmashell 6.1.5"));
        assert!(should_run_plasma_migration("plasmashell 6.0"));
        assert!(!should_run_plasma_migration("plasmashell 5.27.11"));
        assert!(!should_run_plasma_migration(""));
        assert!(!should_run_plasma_migration("not a version"));
        assert_eq!(parse_plasma_version("plasmashell 6.1.5"), Some((6, 1)));
    }
}
