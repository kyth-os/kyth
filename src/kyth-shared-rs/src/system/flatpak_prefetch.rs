//! Offline Flatpak prefetch schedule preference.

use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FlatpakPrefetchConfig {
    pub enabled: bool,
    pub time: String,
}

impl Default for FlatpakPrefetchConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            time: "02:00".into(),
        }
    }
}

/// Parse "HH:MM" strictly; returns None for anything outside 00:00–23:59.
fn parse_time(value: &str) -> Option<(u32, u32)> {
    let (hour, minute) = value.split_once(':')?;
    // Exactly two components: "1:2:3" and "12:" are rejected.
    if minute.contains(':') {
        return None;
    }
    let hour: u32 = hour.parse().ok()?;
    let minute: u32 = minute.parse().ok()?;
    (hour <= 23 && minute <= 59).then_some((hour, minute))
}

fn normalize_time(value: &str) -> String {
    match parse_time(value) {
        Some((hour, minute)) => format!("{hour:02}:{minute:02}"),
        None => "02:00".into(),
    }
}

pub fn config_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path {
        return path.as_ref().to_path_buf();
    }
    if std::env::var("KYTH_TEST_MODE").ok().as_deref() == Some("1") {
        if let Some(config) = std::env::var_os("XDG_CONFIG_HOME") {
            return PathBuf::from(config).join("kyth/flatpak-prefetch.toml");
        }
    }
    PathBuf::from("/etc/kyth/flatpak-prefetch.toml")
}

pub fn load(path: impl AsRef<Path>) -> FlatpakPrefetchConfig {
    let Ok(raw) = std::fs::read_to_string(path) else {
        return FlatpakPrefetchConfig::default();
    };
    let Ok(value) = raw.parse::<toml::Value>() else {
        return FlatpakPrefetchConfig::default();
    };
    FlatpakPrefetchConfig {
        enabled: value
            .get("enabled")
            .and_then(toml::Value::as_bool)
            .unwrap_or(false),
        time: normalize_time(
            value
                .get("time")
                .and_then(toml::Value::as_str)
                .unwrap_or("02:00"),
        ),
    }
}

pub fn save(path: impl AsRef<Path>, config: &FlatpakPrefetchConfig) -> std::io::Result<()> {
    crate::atomic_io::atomic_write_text(
        path,
        &format!(
            "# Kyth flatpak prefetch — offline\nenabled = {}\ntime = {:?}\n",
            config.enabled,
            normalize_time(&config.time)
        ),
        Some(0o600),
    )
}

pub fn status(service: impl AsRef<Path>) -> &'static str {
    if service.as_ref().is_file() {
        "enabled"
    } else {
        "off"
    }
}

pub fn render_service() -> &'static str {
    "[Unit]\nDescription=Kyth flatpak prefetch — off-peak\n[Service]\nType=oneshot\nExecStart=/usr/bin/flatpak update --no-deploy -y\nNice=10\nIOSchedulingClass=best-effort\nIOSchedulingPriority=7\n"
}

pub fn render_timer(config: &FlatpakPrefetchConfig) -> String {
    // Defense in depth: render_timer is pub and may see a config that never
    // went through normalize_time. Never emit an invalid OnCalendar.
    let (hour, minute) = parse_time(&config.time).unwrap_or((2, 0));
    format!("[Unit]\nDescription=Kyth flatpak prefetch timer\n[Timer]\nOnCalendar=*-*-* {hour:02}:{minute:02}:00\nPersistent=true\n[Install]\nWantedBy=timers.target\n")
}

pub fn generate(
    config: &FlatpakPrefetchConfig,
    service: impl AsRef<Path>,
    timer: impl AsRef<Path>,
) -> std::io::Result<Option<PathBuf>> {
    let service = service.as_ref();
    let timer = timer.as_ref();
    if !config.enabled {
        for path in [service, timer] {
            crate::atomic_io::remove_if_exists(path)?;
        }
        return Ok(None);
    }
    crate::atomic_io::atomic_write_text(service, render_service(), Some(0o644))?;
    crate::atomic_io::atomic_write_text(timer, &render_timer(config), Some(0o644))?;
    Ok(Some(service.to_path_buf()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn rejects_out_of_range_and_non_numeric_times() {
        // "99:99" and "ab:cd" previously passed through and produced an
        // OnCalendar systemd would reject, leaving the timer silently dead.
        for bad in ["99:99", "ab:cd", "24:00", "12:60", "1:2:3", "", "12", ":30"] {
            assert_eq!(normalize_time(bad), "02:00", "bad time: {bad}");
            let timer = render_timer(&FlatpakPrefetchConfig {
                enabled: true,
                time: bad.into(),
            });
            assert!(
                timer.contains("*-*-* 02:00:00"),
                "render must fall back, bad time: {bad}"
            );
        }
        assert_eq!(normalize_time("23:30"), "23:30");
        assert_eq!(normalize_time("2:5"), "02:05");
        assert_eq!(normalize_time("00:00"), "00:00");
    }

    #[test]
    fn defaults_and_normalizes_schedule() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("prefetch.toml");
        std::fs::write(&path, "enabled = true\ntime = \"invalid\"\n").unwrap();
        assert_eq!(
            load(&path),
            FlatpakPrefetchConfig {
                enabled: true,
                time: "02:00".into()
            }
        );
        save(
            &path,
            &FlatpakPrefetchConfig {
                enabled: true,
                time: "23:30".into(),
            },
        )
        .unwrap();
        assert_eq!(load(&path).time, "23:30");
    }
}
