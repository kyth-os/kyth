//! Battery configuration and health reads.
//!
//! Configuration writes use the shared atomic replacement helper. Sysfs health
//! reads are best-effort and never make a device mutation.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

const DEFAULT_START: i64 = 40;
const DEFAULT_STOP: i64 = 80;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BatteryConfig {
    pub charge_start: i64,
    pub charge_stop: i64,
    pub health_check: bool,
}

impl Default for BatteryConfig {
    fn default() -> Self {
        Self {
            charge_start: DEFAULT_START,
            charge_stop: DEFAULT_STOP,
            health_check: true,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct BatteryHealth {
    pub capacity: String,
    pub cycles: String,
}

/// System-wide config the Hub syncs the user's `battery.toml` to; the
/// daemon prefers this when present so the per-user file is not required
/// at boot. Falls back to the per-user path otherwise.
pub const SYSTEM_CONFIG_PATH: &str = "/etc/kyth/battery.toml";
/// Cap for the JSONL health ledger; `append_ledger` trims past this.
pub const LEDGER_MAX_LINES: usize = 500;

pub fn system_battery_config_path() -> PathBuf {
    PathBuf::from(SYSTEM_CONFIG_PATH)
}

/// Daemon view of the config: explicit system path first, per-user file
/// as fallback.
pub fn load_battery_with_fallback(
    system: impl AsRef<Path>,
    user: impl AsRef<Path>,
) -> BatteryConfig {
    if system.as_ref().is_file() {
        load_battery(system)
    } else {
        load_battery(user)
    }
}

pub fn battery_config_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path {
        return path.as_ref().to_path_buf();
    }
    if let Some(config) = std::env::var_os("XDG_CONFIG_HOME") {
        return PathBuf::from(config).join("kyth/battery.toml");
    }
    PathBuf::from(std::env::var_os("HOME").unwrap_or_else(|| ".".into()))
        .join(".config/kyth/battery.toml")
}

fn clamp_config(config: BatteryConfig) -> BatteryConfig {
    BatteryConfig {
        charge_start: config.charge_start.clamp(20, 50),
        charge_stop: config.charge_stop.clamp(60, 100),
        health_check: config.health_check,
    }
}

pub fn load_battery(path: impl AsRef<Path>) -> BatteryConfig {
    let Ok(raw) = fs::read_to_string(path) else {
        return BatteryConfig::default();
    };
    let Ok(value) = raw.parse::<toml::Value>() else {
        return BatteryConfig::default();
    };
    let table = value.as_table();
    clamp_config(BatteryConfig {
        charge_start: table
            .and_then(|table| table.get("charge_start"))
            .and_then(toml::Value::as_integer)
            .unwrap_or(DEFAULT_START),
        charge_stop: table
            .and_then(|table| table.get("charge_stop"))
            .and_then(toml::Value::as_integer)
            .unwrap_or(DEFAULT_STOP),
        health_check: table
            .and_then(|table| table.get("health_check"))
            .and_then(toml::Value::as_bool)
            .unwrap_or(true),
    })
}

pub fn load_battery_default() -> BatteryConfig {
    load_battery(battery_config_path(None::<PathBuf>))
}

pub fn save_battery(path: impl AsRef<Path>, config: &BatteryConfig) -> std::io::Result<()> {
    let config = clamp_config(config.clone());
    let text = format!(
        "# Kyth battery — charge thresholds, offline\ncharge_start = {}\ncharge_stop = {}\nhealth_check = {}\n",
        config.charge_start, config.charge_stop, config.health_check
    );
    crate::atomic_io::atomic_write_text(path, &text, Some(0o600))
}

pub fn read_battery_health_in(root: impl AsRef<Path>) -> BTreeMap<String, BatteryHealth> {
    let mut health = BTreeMap::new();
    let Ok(entries) = fs::read_dir(root) else {
        return health;
    };
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().to_string();
        if !name.starts_with("BAT") {
            continue;
        }
        let directory = entry.path();
        let read = |file: &str| {
            fs::read_to_string(directory.join(file))
                .map(|value| value.trim().to_string())
                .unwrap_or_else(|_| "?".to_string())
        };
        health.insert(
            name,
            BatteryHealth {
                capacity: read("capacity"),
                cycles: read("cycle_count"),
            },
        );
    }
    health
}

pub fn read_battery_health() -> BTreeMap<String, BatteryHealth> {
    read_battery_health_in("/sys/class/power_supply")
}

/// Default ledger path for periodic health snapshots.
pub const LEDGER_PATH: &str = "/var/cache/kyth/battery.jsonl";

/// Current UTC timestamp in ISO-8601 form, mirroring
/// `datetime.utcnow().isoformat()`.
pub fn utc_now_iso() -> String {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|span| span.as_secs() as libc::time_t)
        .unwrap_or(0);
    let mut broken = unsafe { std::mem::zeroed::<libc::tm>() };
    unsafe { libc::gmtime_r(&now, &mut broken) };
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}",
        broken.tm_year + 1900,
        broken.tm_mon + 1,
        broken.tm_mday,
        broken.tm_hour,
        broken.tm_min,
        broken.tm_sec
    )
}

/// Append one health snapshot line to the JSONL ledger, creating parent
/// directories as needed. Failures are swallowed by the caller.
pub fn append_ledger(
    path: &Path,
    health: &BTreeMap<String, BatteryHealth>,
    config: &BatteryConfig,
) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let entry = serde_json::json!({
        "health": health,
        "cfg": {
            "charge_start": config.charge_start,
            "charge_stop": config.charge_stop,
            "health_check": config.health_check,
        },
        "ts": utc_now_iso(),
    });
    use std::io::Write;
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)?;
    writeln!(
        file,
        "{}",
        serde_json::to_string(&entry).unwrap_or_default()
    )?;
    // Bound the ledger: health snapshots append every 30 s forever, so
    // trim past the cap instead of growing without limit.
    let _ = cap_ledger(path, LEDGER_MAX_LINES);
    Ok(())
}

/// Trim a JSONL ledger to its newest `max_lines` lines. Missing files are
/// a no-op error the caller may ignore.
pub fn cap_ledger(path: &Path, max_lines: usize) -> std::io::Result<()> {
    let raw = fs::read_to_string(path)?;
    let lines: Vec<&str> = raw.lines().collect();
    if lines.len() <= max_lines {
        return Ok(());
    }
    fs::write(path, lines[lines.len() - max_lines..].join("\n") + "\n")
}

/// Batteries exposing at least one charge-control file under `root`;
/// desktops without a controllable battery yield an empty list.
pub fn controllable_batteries_in(root: impl AsRef<Path>) -> Vec<String> {
    let Ok(entries) = fs::read_dir(root) else {
        return Vec::new();
    };
    entries
        .flatten()
        .filter(|entry| {
            let name = entry.file_name().to_string_lossy().into_owned();
            name.starts_with("BAT")
                && [
                    "charge_control_start_threshold",
                    "charge_control_end_threshold",
                ]
                .iter()
                .any(|file| entry.path().join(file).is_file())
        })
        .map(|entry| entry.file_name().to_string_lossy().into_owned())
        .collect()
}

/// Write the charge-start and charge-stop thresholds to every battery,
/// but only where the control file is present. Returns how many
/// batteries were controlled.
pub fn apply_thresholds_in(root: impl AsRef<Path>, start: i64, stop: i64) -> usize {
    let Ok(entries) = fs::read_dir(root) else {
        return 0;
    };
    let mut controlled = 0;
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        if !name.starts_with("BAT") {
            continue;
        }
        let mut touched = false;
        for (file, value) in [
            ("charge_control_start_threshold", start),
            ("charge_control_end_threshold", stop),
        ] {
            let target = entry.path().join(file);
            if target.is_file() && fs::write(&target, value.to_string()).is_ok() {
                touched = true;
            }
        }
        if touched {
            controlled += 1;
        }
    }
    controlled
}

/// Write the charge-stop threshold to every battery's control file.
/// Missing files and write failures are skipped.
pub fn apply_threshold(stop: i64) {
    let Ok(entries) = fs::read_dir("/sys/class/power_supply") else {
        return;
    };
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        if !name.starts_with("BAT") {
            continue;
        }
        let _ = fs::write(
            entry.path().join("charge_control_end_threshold"),
            stop.to_string(),
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn loads_defaults_and_clamps_values() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("battery.toml");
        fs::write(
            &path,
            "charge_start = 5\ncharge_stop = 120\nhealth_check = false\n",
        )
        .unwrap();
        assert_eq!(
            load_battery(&path),
            BatteryConfig {
                charge_start: 20,
                charge_stop: 100,
                health_check: false
            }
        );
        assert_eq!(
            load_battery(directory.path().join("missing.toml")),
            BatteryConfig::default()
        );
    }

    #[test]
    fn system_config_wins_over_user_config() {
        let directory = tempdir().unwrap();
        let system = directory.path().join("system.toml");
        let user = directory.path().join("user.toml");
        fs::write(&system, "charge_start = 45\ncharge_stop = 85\n").unwrap();
        fs::write(&user, "charge_start = 20\ncharge_stop = 60\n").unwrap();
        assert_eq!(
            load_battery_with_fallback(&system, &user),
            BatteryConfig {
                charge_start: 45,
                charge_stop: 85,
                health_check: true
            }
        );
        assert_eq!(
            load_battery_with_fallback(directory.path().join("absent.toml"), &user),
            BatteryConfig {
                charge_start: 20,
                charge_stop: 60,
                health_check: true
            }
        );
    }

    #[test]
    fn thresholds_apply_only_where_control_files_exist() {
        let directory = tempdir().unwrap();
        let full = directory.path().join("BAT0");
        let partial = directory.path().join("BAT1");
        let bare = directory.path().join("BAT2");
        for dir in [&full, &partial, &bare] {
            fs::create_dir(dir).unwrap();
        }
        fs::write(full.join("charge_control_start_threshold"), "0").unwrap();
        fs::write(full.join("charge_control_end_threshold"), "0").unwrap();
        fs::write(partial.join("charge_control_end_threshold"), "0").unwrap();
        assert_eq!(controllable_batteries_in(directory.path()).len(), 2);
        assert_eq!(apply_thresholds_in(directory.path(), 45, 85), 2);
        assert_eq!(
            fs::read_to_string(full.join("charge_control_start_threshold")).unwrap(),
            "45"
        );
        assert_eq!(
            fs::read_to_string(full.join("charge_control_end_threshold")).unwrap(),
            "85"
        );
        assert_eq!(
            fs::read_to_string(partial.join("charge_control_end_threshold")).unwrap(),
            "85"
        );
        assert!(!partial.join("charge_control_start_threshold").exists());
        assert!(!bare.join("charge_control_end_threshold").exists());
    }

    #[test]
    fn empty_power_supply_tree_has_no_controllable_battery() {
        let directory = tempdir().unwrap();
        assert!(controllable_batteries_in(directory.path()).is_empty());
        assert_eq!(apply_thresholds_in(directory.path(), 45, 85), 0);
        assert!(controllable_batteries_in(directory.path().join("missing")).is_empty());
    }

    #[test]
    fn ledger_is_capped_to_the_newest_lines() {
        let directory = tempdir().unwrap();
        let ledger = directory.path().join("battery.jsonl");
        fs::write(&ledger, "a\nb\nc\nd\ne\n").unwrap();
        cap_ledger(&ledger, 3).unwrap();
        assert_eq!(fs::read_to_string(&ledger).unwrap(), "c\nd\ne\n");
        cap_ledger(&ledger, 3).unwrap();
        assert_eq!(fs::read_to_string(&ledger).unwrap(), "c\nd\ne\n");
    }

    #[test]
    fn ledger_appends_timestamped_health_snapshots() {
        let directory = tempdir().unwrap();
        let ledger = directory.path().join("nested/battery.jsonl");
        let mut health = BTreeMap::new();
        health.insert(
            "BAT0".to_string(),
            super::BatteryHealth {
                capacity: "87".to_string(),
                cycles: "12".to_string(),
            },
        );
        super::append_ledger(&ledger, &health, &super::BatteryConfig::default()).unwrap();
        let line = fs::read_to_string(&ledger).unwrap();
        let entry: serde_json::Value = serde_json::from_str(line.trim()).unwrap();
        assert_eq!(entry["cfg"]["charge_stop"], 80);
        assert_eq!(entry["health"]["BAT0"]["cycles"], "12");
        assert!(entry["ts"].as_str().is_some_and(|ts| ts.len() == 19));
        assert!(super::utc_now_iso().len() == 19);
    }

    #[test]
    fn saves_clamped_config_atomically() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("battery.toml");
        save_battery(
            &path,
            &BatteryConfig {
                charge_start: 1,
                charge_stop: 101,
                health_check: true,
            },
        )
        .unwrap();
        assert_eq!(
            load_battery(&path),
            BatteryConfig {
                charge_start: 20,
                charge_stop: 100,
                health_check: true
            }
        );
    }

    #[test]
    fn reads_battery_sysfs_shape_without_real_sysfs() {
        let directory = tempdir().unwrap();
        let battery = directory.path().join("BAT0");
        fs::create_dir(&battery).unwrap();
        fs::write(battery.join("capacity"), "87\n").unwrap();
        fs::write(battery.join("cycle_count"), "123\n").unwrap();
        let result = read_battery_health_in(directory.path());
        assert_eq!(
            result["BAT0"],
            BatteryHealth {
                capacity: "87".into(),
                cycles: "123".into()
            }
        );
    }
}
