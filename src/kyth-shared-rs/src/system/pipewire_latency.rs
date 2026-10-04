//! PipeWire low-latency presets: app → quantum map to conf drop-ins.
//!
//! Mirrors `kyth_shared.pipewire_latency`: a `default` (or `*`) entry sets
//! the session clock quantum drop-in; named apps keep an env map for launch
//! wrappers (`PIPEWIRE_LATENCY=quantum/rate`). Only the `*_bin.rs` entry
//! point touches the live filesystem.

use std::collections::BTreeMap;
use std::os::unix::fs::{symlink, PermissionsExt};
use std::path::{Path, PathBuf};

pub const DEFAULT_RATE: i64 = 48000;
pub const TTL_PATH: &str = "/run/kyth-pipewire-ttl";
pub const TTL_SECS: u64 = 30;

pub fn config_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path {
        return path.as_ref().to_path_buf();
    }
    if let Some(xdg) = std::env::var_os("XDG_CONFIG_HOME") {
        return PathBuf::from(xdg).join("kyth/pipewire-latency.toml");
    }
    let home = std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_default();
    home.join(".config/kyth/pipewire-latency.toml")
}

pub fn xdg_config() -> PathBuf {
    if let Some(xdg) = std::env::var_os("XDG_CONFIG_HOME") {
        return PathBuf::from(xdg);
    }
    let home = std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_default();
    home.join(".config")
}

fn clamp_quantum(value: &toml::Value) -> Option<i64> {
    // Mirrors Python int(raw): truncates floats, parses numeric strings,
    // maps bools via 0/1; anything else is skipped.
    let raw = value
        .as_integer()
        .or_else(|| value.as_float().map(|v| v as i64))
        .or_else(|| value.as_str().and_then(|s| s.parse::<i64>().ok()))
        .or_else(|| value.as_bool().map(|b| i64::from(b)))?;
    Some(raw.clamp(16, 2048))
}

pub fn load(path: impl AsRef<Path>) -> BTreeMap<String, i64> {
    let Ok(raw) = std::fs::read_to_string(path) else {
        return BTreeMap::new();
    };
    let Ok(value) = raw.parse::<toml::Value>() else {
        return BTreeMap::new();
    };
    value
        .get("apps")
        .and_then(toml::Value::as_table)
        .map(|apps| {
            apps.iter()
                .filter_map(|(name, quantum)| clamp_quantum(quantum).map(|q| (name.clone(), q)))
                .collect()
        })
        .unwrap_or_default()
}

pub fn default_quantum(apps: &BTreeMap<String, i64>) -> Option<i64> {
    apps.get("default").or_else(|| apps.get("*")).copied()
}

pub fn render_quantum_dropin(quantum: i64) -> String {
    format!(
        "# Kyth PipeWire latency — default quantum {quantum}\ncontext.properties = {{\n  default.clock.quantum = {quantum}\n}}\n"
    )
}

/// App names come from a user-owned TOML file while this output is sourced
/// or parsed by launch helpers. Escape newlines/control characters so a
/// key cannot inject arbitrary lines into the env map (same approach as
/// input_preset.rs).
fn safe_app_name(name: &str) -> String {
    name.chars()
        .map(|character| match character {
            '\n' => String::from("\\n"),
            '\r' => String::from("\\r"),
            c if c.is_control() => format!("\\u{{{:x}}}", c as u32),
            c => c.to_string(),
        })
        .collect()
}

pub fn render_env_map(named: &BTreeMap<String, i64>, rate: i64) -> String {
    let mut text =
        String::from("# Kyth PipeWire per-app latency — source or parse from launch helpers\n");
    text.push_str(&format!("# rate={rate}\n"));
    for (app, quantum) in named {
        let app = safe_app_name(app);
        text.push_str(&format!("{app}=PIPEWIRE_LATENCY={quantum}/{rate}\n"));
    }
    text
}

enum DropinSnapshot {
    Missing,
    File { contents: Vec<u8>, mode: u32 },
    Symlink(PathBuf),
}

fn snapshot_dropin(path: &Path) -> std::io::Result<DropinSnapshot> {
    let metadata = match std::fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Ok(DropinSnapshot::Missing)
        }
        Err(error) => return Err(error),
    };
    if metadata.file_type().is_symlink() {
        return Ok(DropinSnapshot::Symlink(std::fs::read_link(path)?));
    }
    if !metadata.is_file() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "PipeWire latency drop-in is not a regular file",
        ));
    }
    Ok(DropinSnapshot::File {
        contents: std::fs::read(path)?,
        mode: metadata.permissions().mode() & 0o7777,
    })
}

fn restore_dropin(path: &Path, snapshot: DropinSnapshot) -> std::io::Result<()> {
    match snapshot {
        DropinSnapshot::Missing => match std::fs::remove_file(path) {
            Ok(()) => Ok(()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(error) => Err(error),
        },
        DropinSnapshot::File { contents, mode } => {
            crate::atomic_io::atomic_write_bytes(path, &contents, Some(mode))
        }
        DropinSnapshot::Symlink(target) => {
            match std::fs::remove_file(path) {
                Ok(()) => {}
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(error) => return Err(error),
            }
            symlink(target, path)
        }
    }
}

/// Applies the preset under `xdg` (drop-in + env map), returning the
/// launcher notes. A failed env-map write restores the prior quantum
/// drop-in so a partial apply is never reported as a failed no-op.
pub fn apply(xdg: &Path, apps: &BTreeMap<String, i64>, rate: i64) -> std::io::Result<Vec<String>> {
    let dropin = xdg.join("pipewire/pipewire.conf.d/99-kyth-latency.conf");
    let env_path = xdg.join("kyth/pipewire-latency.env");
    let previous_dropin = snapshot_dropin(&dropin)?;
    let mut applied = Vec::new();
    match default_quantum(apps) {
        Some(quantum) => {
            crate::atomic_io::atomic_write_text(&dropin, &render_quantum_dropin(quantum), None)?;
            applied.push(format!("quantum={quantum} → {}", dropin.display()));
        }
        None => {
            if dropin.exists() && std::fs::remove_file(&dropin).is_ok() {
                applied.push(format!("removed {}", dropin.display()));
            }
        }
    }
    let mut ordered = BTreeMap::new();
    for (name, quantum) in apps
        .iter()
        .filter(|(name, _)| name.as_str() != "default" && name.as_str() != "*")
    {
        ordered.insert(name.clone(), *quantum);
    }
    if let Err(error) =
        crate::atomic_io::atomic_write_text(&env_path, &render_env_map(&ordered, rate), None)
    {
        if let Err(restore_error) = restore_dropin(&dropin, previous_dropin) {
            return Err(std::io::Error::new(
                error.kind(),
                format!("{error}; failed to restore prior PipeWire drop-in: {restore_error}"),
            ));
        }
        return Err(error);
    }
    applied.push(format!("{} apps → {}", ordered.len(), env_path.display()));
    Ok(applied)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn clamps_and_skips_bad_quantums() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("pipewire-latency.toml");
        std::fs::write(
            &path,
            "[apps]\nok = 64\nbig = 99999\nbad = \"x\"\nstar = 128\n",
        )
        .unwrap();
        let apps = load(&path);
        assert_eq!(apps.get("ok"), Some(&64));
        assert_eq!(apps.get("big"), Some(&2048));
        assert_eq!(apps.get("star"), Some(&128));
        assert!(!apps.contains_key("bad"));
        assert!(load(dir.path().join("missing.toml")).is_empty());
    }

    #[test]
    fn default_key_order_prefers_default_over_star() {
        let mut apps = BTreeMap::new();
        apps.insert("*".into(), 128);
        apps.insert("default".into(), 256);
        assert_eq!(default_quantum(&apps), Some(256));
    }

    #[test]
    fn renders_dropin_and_env_map_like_python() {
        assert_eq!(
            render_quantum_dropin(256),
            "# Kyth PipeWire latency — default quantum 256\ncontext.properties = {\n  default.clock.quantum = 256\n}\n"
        );
        let mut named = BTreeMap::new();
        named.insert("game".to_string(), 64);
        assert_eq!(
            render_env_map(&named, 48000),
            "# Kyth PipeWire per-app latency — source or parse from launch helpers\n# rate=48000\ngame=PIPEWIRE_LATENCY=64/48000\n"
        );
    }

    #[test]
    fn app_names_cannot_inject_env_lines() {
        let mut named = BTreeMap::new();
        named.insert("evil\nINJECTED=1".to_string(), 64);
        named.insert("cr\rev".to_string(), 128);
        let rendered = render_env_map(&named, 48000);
        // Every app entry stays on exactly one line: no raw newlines survive.
        for line in rendered.lines().skip(2) {
            assert!(!line.contains('\n') && !line.contains('\r'));
        }
        assert!(rendered.contains("evil\\nINJECTED=1=PIPEWIRE_LATENCY=64/48000\n"));
        assert!(rendered.contains("cr\\rev=PIPEWIRE_LATENCY=128/48000\n"));
        assert!(!rendered.contains("INJECTED=1\n"));
    }

    #[test]
    fn failed_env_write_removes_new_quantum_dropin() {
        let dir = tempdir().unwrap();
        let blocker = dir.path().join("kyth");
        std::fs::write(&blocker, "not a directory").unwrap();
        let mut apps = BTreeMap::new();
        apps.insert("default".into(), 256);

        assert!(apply(dir.path(), &apps, DEFAULT_RATE).is_err());

        assert!(!dir
            .path()
            .join("pipewire/pipewire.conf.d/99-kyth-latency.conf")
            .exists());
    }

    #[test]
    fn failed_env_write_restores_existing_quantum_dropin() {
        let dir = tempdir().unwrap();
        let dropin = dir
            .path()
            .join("pipewire/pipewire.conf.d/99-kyth-latency.conf");
        std::fs::create_dir_all(dropin.parent().unwrap()).unwrap();
        std::fs::write(&dropin, "previous quantum configuration").unwrap();
        let mut permissions = std::fs::metadata(&dropin).unwrap().permissions();
        permissions.set_mode(0o600);
        std::fs::set_permissions(&dropin, permissions).unwrap();
        let blocker = dir.path().join("kyth");
        std::fs::write(&blocker, "not a directory").unwrap();
        let mut apps = BTreeMap::new();
        apps.insert("default".into(), 256);

        assert!(apply(dir.path(), &apps, DEFAULT_RATE).is_err());

        assert_eq!(
            std::fs::read_to_string(&dropin).unwrap(),
            "previous quantum configuration"
        );
        assert_eq!(
            std::fs::metadata(dropin).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }

    #[test]
    fn failed_env_write_restores_removed_quantum_symlink() {
        let dir = tempdir().unwrap();
        let target = dir.path().join("shared-pipewire.conf");
        std::fs::write(&target, "shared configuration").unwrap();
        let dropin = dir
            .path()
            .join("pipewire/pipewire.conf.d/99-kyth-latency.conf");
        std::fs::create_dir_all(dropin.parent().unwrap()).unwrap();
        std::os::unix::fs::symlink(&target, &dropin).unwrap();
        let blocker = dir.path().join("kyth");
        std::fs::write(&blocker, "not a directory").unwrap();

        assert!(apply(dir.path(), &BTreeMap::new(), DEFAULT_RATE).is_err());

        assert!(std::fs::symlink_metadata(&dropin)
            .unwrap()
            .file_type()
            .is_symlink());
        assert_eq!(std::fs::read_link(dropin).unwrap(), target);
    }

    #[test]
    fn applies_dropin_and_removes_stale_one() {
        let dir = tempdir().unwrap();
        let mut apps = BTreeMap::new();
        apps.insert("default".into(), 256);
        apps.insert("game".into(), 64);
        let notes = apply(dir.path(), &apps, DEFAULT_RATE).unwrap();
        assert_eq!(notes.len(), 2);
        assert!(notes[0].starts_with("quantum=256 → "));
        assert!(notes[1].starts_with("1 apps → "));
        let dropin = dir
            .path()
            .join("pipewire/pipewire.conf.d/99-kyth-latency.conf");
        assert!(dropin.is_file());
        let notes = apply(dir.path(), &BTreeMap::new(), DEFAULT_RATE).unwrap();
        assert!(!dropin.exists());
        assert!(notes.iter().any(|note| note.starts_with("removed ")));
        assert!(notes.iter().any(|note| note.starts_with("0 apps → ")));
    }
}
