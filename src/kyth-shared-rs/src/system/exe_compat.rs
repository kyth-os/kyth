//! Offline EXE compatibility lookup by bounded SHA-256 or filename.

use regex::Regex;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::path::Path;

pub const DEFAULT_COMPAT_PATH: &str = "/usr/share/kyth/compat.json";
const HASH_BYTES: usize = 1 << 20;

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct CompatResult {
    pub status: String,
    pub runner: String,
    pub reason: String,
}

pub fn normalise_filename(filename: &str) -> String {
    let stem = Path::new(filename)
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    let separators = Regex::new(r"[\s.]+").expect("static filename separator pattern");
    let wrapper = Regex::new(r"^(setup|install|installer|update|updater|launcher)[-_]+")
        .expect("static wrapper prefix pattern");
    let wrapper_suffix = Regex::new(r"[-_]+(setup|install|installer|update|updater|launcher)$")
        .expect("static wrapper suffix pattern");
    let token = Regex::new(r"[-_]+(x64|x86|x86_64|amd64|win64|win32|windows|pc|arm64|online|offline|stable|v?\d[\d.]*)$").expect("static release token pattern");
    let mut stem = separators.replace_all(&stem, "-").into_owned();
    for _ in 0..4 {
        let old = stem.clone();
        stem = wrapper.replace(&stem, "").into_owned();
        stem = wrapper_suffix.replace(&stem, "").into_owned();
        stem = token.replace(&stem, "").into_owned();
        if stem == old {
            break;
        }
    }
    stem
}

pub fn is_rpm_installer(filename: &str) -> bool {
    filename.to_ascii_lowercase().ends_with(".rpm")
}

pub fn rewrite_steam_exec(exec_line: &str) -> Option<String> {
    let target = exec_line.split_once('=')?.1.trim();
    let game_pattern = Regex::new(r"steam://rungameid/([0-9]+)").expect("static Steam URI pattern");
    if let Some(capture) = game_pattern
        .captures(target)
        .and_then(|capture| capture.get(1))
    {
        return Some(format!(
            "Exec=flatpak run com.valvesoftware.Steam steam://rungameid/{}",
            capture.as_str()
        ));
    }
    let app_pattern = Regex::new(r"-applaunch\s+([0-9]+)").expect("static Steam applaunch pattern");
    app_pattern
        .captures(target)
        .and_then(|capture| capture.get(1))
        .map(|capture| {
            format!(
                "Exec=flatpak run com.valvesoftware.Steam steam://rungameid/{}",
                capture.as_str()
            )
        })
}

pub const BOTTLES_FLATPAK_ID: &str = "com.usebottles.bottles";
/// Hint printed when Bottles is the suggested runner. Bottles ships as a
/// Flatpak, so a bare `bottles-cli` only resolves on native installs.
pub const BOTTLES_FLATPAK_HINT: &str =
    "flatpak run --command=bottles-cli com.usebottles.bottles run <exe>";

fn path_has(program: &str) -> bool {
    std::env::var_os("PATH")
        .map(|paths| {
            std::env::split_paths(&paths).any(|dir| {
                dir.join(program).is_file() || dir.join(format!("{program}.exe")).is_file()
            })
        })
        .unwrap_or(false)
}

/// True when a native Bottles runner is on PATH.
pub fn bottles_native_available() -> bool {
    path_has("bottles-cli") || path_has("bottles")
}

/// True when the Bottles Flatpak is installed (user or system scope).
/// Pure filesystem check so availability gating never shells out.
pub fn bottles_flatpak_installed(home: &Path) -> bool {
    home.join(".local/share/flatpak/app")
        .join(BOTTLES_FLATPAK_ID)
        .is_dir()
        || Path::new("/var/lib/flatpak/app")
            .join(BOTTLES_FLATPAK_ID)
            .is_dir()
}

/// True when any usable Bottles runner exists (native or Flatpak).
pub fn bottles_available(home: &Path) -> bool {
    bottles_native_available() || bottles_flatpak_installed(home)
}

/// Runner suggestion for `<exe>`: native form only when a native runner is
/// on PATH, otherwise the Flatpak form that matches how KythOS ships Bottles.
pub fn bottles_run_hint(exe: &str) -> String {
    if bottles_native_available() {
        format!("Run with: bottles-cli run {exe}  or  Lutris")
    } else {
        format!(
            "Run with: {}  or  Lutris",
            BOTTLES_FLATPAK_HINT.replace("<exe>", exe)
        )
    }
}

pub fn load_compat(path: impl AsRef<Path>) -> Value {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|text| serde_json::from_str(&text).ok())
        .filter(Value::is_object)
        .unwrap_or_else(|| serde_json::json!({"entries": {}}))
}

fn bounded_hash(path: &Path) -> Option<String> {
    let bytes = std::fs::read(path).ok()?;
    let mut hasher = Sha256::new();
    hasher.update(&bytes[..bytes.len().min(HASH_BYTES)]);
    Some(format!("{:x}", hasher.finalize())[..12].to_string())
}

fn entry_result(entry: &Value) -> CompatResult {
    CompatResult {
        status: entry
            .get("status")
            .and_then(Value::as_str)
            .unwrap_or("Works")
            .to_string(),
        runner: entry
            .get("runner")
            .and_then(Value::as_str)
            .unwrap_or("Wine")
            .to_string(),
        reason: entry
            .get("reason")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
    }
}

pub fn check_exe(path: impl AsRef<Path>, compat: &Value) -> CompatResult {
    let path = path.as_ref();
    let entries = compat.get("entries").and_then(Value::as_object);
    let hash = bounded_hash(path);
    let filename = path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if let Some(entry) = hash
        .as_deref()
        .and_then(|key| entries.and_then(|entries| entries.get(key)))
        .or_else(|| entries.and_then(|entries| entries.get(&filename)))
    {
        return entry_result(entry);
    }
    for marker in ["easyanticheat", "eac", "vgc", "battleye"] {
        if filename.contains(marker) {
            return CompatResult {
                status: "Blocked".to_string(),
                runner: "Anti-cheat".to_string(),
                reason: format!("Contains {marker} — blocked"),
            };
        }
    }
    CompatResult {
        status: "Works".to_string(),
        runner: "Bottles".to_string(),
        reason: "Offline DB: best-effort Wine".to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn uses_filename_then_anticheat_fallback() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("game.exe");
        fs::write(&path, "demo").unwrap();
        let compat = serde_json::json!({"entries":{"game.exe":{"status":"Gold","runner":"Proton","reason":"tested"}}});
        assert_eq!(check_exe(&path, &compat).status, "Gold");
        let blocked = directory.path().join("easyanticheat.exe");
        fs::write(&blocked, "demo").unwrap();
        assert_eq!(
            check_exe(&blocked, &serde_json::json!({"entries":{}})).status,
            "Blocked"
        );
    }

    #[test]
    fn flatpak_hint_when_no_native_runner() {
        // KythOS ships Bottles as a Flatpak: without bottles-cli on PATH the
        // hint must use the flatpak run form, never a bare `bottles-cli`.
        // (PATH lookup is environment-dependent; assert the documented
        // constant and the substitution contract instead.)
        assert!(BOTTLES_FLATPAK_HINT.contains("flatpak run --command=bottles-cli"));
        assert!(BOTTLES_FLATPAK_HINT.contains("com.usebottles.bottles"));
        let hint = bottles_run_hint("game.exe");
        if bottles_native_available() {
            assert_eq!(hint, "Run with: bottles-cli run game.exe  or  Lutris");
        } else {
            assert!(hint.contains("flatpak run --command=bottles-cli"));
            assert!(hint.contains("game.exe"));
        }
    }

    #[test]
    fn flatpak_marker_dirs_count_as_installed() {
        // User-scope marker under $HOME always counts, regardless of what
        // the host has installed system-wide.
        let home = tempfile::tempdir().unwrap();
        let marker = home
            .path()
            .join(".local/share/flatpak/app/com.usebottles.bottles");
        assert!(!marker.is_dir());
        std::fs::create_dir_all(&marker).unwrap();
        assert!(bottles_flatpak_installed(home.path()));
        assert!(bottles_available(home.path()));
    }

    #[test]
    fn normalizes_installer_names_and_rewrites_steam_launchers() {
        assert_eq!(
            normalise_filename("/tmp/Setup My.Game v1.2 x64.exe"),
            "my-game"
        );
        assert!(is_rpm_installer("driver.RPM"));
        assert_eq!(
            rewrite_steam_exec("Exec=steam -applaunch 123"),
            Some("Exec=flatpak run com.valvesoftware.Steam steam://rungameid/123".into())
        );
        assert_eq!(
            rewrite_steam_exec("Exec=steam://rungameid/456"),
            Some("Exec=flatpak run com.valvesoftware.Steam steam://rungameid/456".into())
        );
        assert_eq!(rewrite_steam_exec("Name=Game"), None);
    }
}
