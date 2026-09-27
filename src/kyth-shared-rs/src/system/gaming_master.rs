//! Read-only gaming master profile and safety decision.

use super::tuning_profile::{config_path, load_profile, Profile};
use std::path::{Path, PathBuf};

pub fn master_config_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    config_path(
        path,
        "/etc/kyth/gaming-performance.toml",
        "gaming-performance.toml",
    )
}

pub fn load_master(path: impl AsRef<Path>) -> Profile {
    load_profile(path)
}

pub fn save_master(path: impl AsRef<Path>, profile: Profile) -> std::io::Result<()> {
    super::tuning_profile::save_profile(path, "Kyth master gaming performance", profile)
}

pub fn thermal_high(root: impl AsRef<Path>, threshold_c: i64) -> bool {
    let Ok(entries) = root.as_ref().read_dir() else {
        return false;
    };
    entries
        .flatten()
        .filter(|entry| {
            entry
                .file_name()
                .to_string_lossy()
                .starts_with("thermal_zone")
        })
        .any(|entry| {
            std::fs::read_to_string(entry.path().join("temp"))
                .ok()
                .and_then(|value| value.trim().parse::<i64>().ok())
                .is_some_and(|temp| temp > threshold_c * 1000)
        })
}

pub fn battery_low(root: impl AsRef<Path>, threshold_pct: i64) -> bool {
    let Ok(entries) = root.as_ref().read_dir() else {
        return false;
    };
    entries
        .flatten()
        .filter(|entry| entry.file_name().to_string_lossy().starts_with("BAT"))
        .any(|entry| {
            let capacity = std::fs::read_to_string(entry.path().join("capacity"))
                .ok()
                .and_then(|value| value.trim().parse::<i64>().ok());
            let status = std::fs::read_to_string(entry.path().join("status"))
                .ok()
                .map(|value| value.trim().to_ascii_lowercase());
            capacity.is_some_and(|capacity| capacity < threshold_pct)
                && status.is_some_and(|status| status == "discharging" || status == "not charging")
        })
}

pub fn effective_gaming(profile: Profile, thermal: bool, battery: bool) -> (Profile, &'static str) {
    if profile != Profile::Gaming {
        return (Profile::Balanced, "balanced profile selected");
    }
    if thermal {
        return (Profile::Balanced, "thermal limit reached");
    }
    if battery {
        return (Profile::Balanced, "battery is low while discharging");
    }
    (Profile::Gaming, "gaming profile ready")
}

#[derive(Debug, Clone)]
pub struct MasterApplyPaths {
    pub kargs_config: PathBuf,
    pub thp_config: PathBuf,
    pub thp_dropin: PathBuf,
    pub irq_config: PathBuf,
    pub irq_dropin: PathBuf,
    pub btrfs_config: PathBuf,
    pub btrfs_dropin: PathBuf,
    pub zswap_config: PathBuf,
    pub zswap_sysctl: PathBuf,
    pub zswap_modprobe: PathBuf,
    pub ananicy_config: PathBuf,
    pub ananicy_rule: PathBuf,
}

fn child_status(name: &str, result: Result<(), String>) -> (String, String) {
    match result {
        Ok(()) => (name.into(), "ok".into()),
        Err(error) => (name.into(), format!("error {error}")),
    }
}

/// Apply sibling tunables for the resolved master profile. irq-tune may
/// skip when isolated_cpus is unset (fail-closed, never bans CPU 1).
pub fn apply_children(gaming: bool, paths: &MasterApplyPaths) -> Vec<(String, String)> {
    let child_profile = if gaming { "kyth" } else { "balanced" };
    let kargs_profile = if gaming { "gaming" } else { "balanced" };
    let mut out = Vec::new();

    let mut kargs = super::gaming_kargs::load_kargs(&paths.kargs_config);
    kargs.profile = kargs_profile.into();
    out.push(child_status(
        "kargs",
        super::gaming_kargs::save_kargs(&paths.kargs_config, &kargs).map_err(|e| e.to_string()),
    ));

    let mut thp = super::extended_preferences::load_thp(&paths.thp_config);
    thp.profile = child_profile.into();
    let thp_result =
        super::extended_preferences::save_thp(&paths.thp_config, &thp).and_then(|_| {
            match super::extended_preferences::thp_dropin(&thp) {
                Some(content) => {
                    crate::atomic_io::atomic_write_text(&paths.thp_dropin, &content, Some(0o644))
                }
                None => match std::fs::remove_file(&paths.thp_dropin) {
                    Ok(()) => Ok(()),
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
                    Err(error) => Err(error),
                },
            }
        });
    out.push(child_status("thp", thp_result.map_err(|e| e.to_string())));

    let mut irq = super::runtime_preferences::load_irq(&paths.irq_config);
    irq.profile = child_profile.into();
    let irq_result = super::runtime_preferences::save_irq(&paths.irq_config, &irq).and_then(|_| {
        super::runtime_preferences::generate_irq(&irq, &paths.irq_dropin, "").map(|_| ())
    });
    out.push(child_status("irq", irq_result.map_err(|e| e.to_string())));

    let mut btrfs = super::btrfs_perf::load(&paths.btrfs_config);
    btrfs.profile = child_profile.into();
    let btrfs_result = super::btrfs_perf::save(&paths.btrfs_config, &btrfs).and_then(|_| {
        super::btrfs_perf::generate(&btrfs, Some(paths.btrfs_dropin.as_path())).map(|_| ())
    });
    out.push(child_status(
        "btrfs",
        btrfs_result.map_err(|e| e.to_string()),
    ));

    let mut zswap = super::zswap::load(&paths.zswap_config);
    zswap.profile = child_profile.into();
    let zswap_result = super::zswap::save(&paths.zswap_config, &zswap).and_then(|_| {
        super::zswap::generate(&zswap, &paths.zswap_sysctl, &paths.zswap_modprobe).map(|_| ())
    });
    out.push(child_status(
        "zswap",
        zswap_result.map_err(|e| e.to_string()),
    ));

    let mut ananicy = super::ananicy::load(&paths.ananicy_config);
    ananicy.profile = child_profile.into();
    let ananicy_result = super::ananicy::save(&paths.ananicy_config, &ananicy)
        .and_then(|_| super::ananicy::generate(&ananicy, &paths.ananicy_rule).map(|_| ()));
    out.push(child_status(
        "ananicy",
        ananicy_result.map_err(|e| e.to_string()),
    ));

    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn honors_thermal_and_battery_safety_gates() {
        let directory = tempdir().unwrap();
        let thermal = directory.path().join("thermal_zone0");
        let battery = directory.path().join("BAT0");
        fs::create_dir(&thermal).unwrap();
        fs::create_dir(&battery).unwrap();
        fs::write(thermal.join("temp"), "90000\n").unwrap();
        fs::write(battery.join("capacity"), "20\n").unwrap();
        fs::write(battery.join("status"), "Discharging\n").unwrap();
        assert!(thermal_high(directory.path(), 85));
        assert!(battery_low(directory.path(), 30));
        assert_eq!(
            effective_gaming(Profile::Gaming, true, false).0,
            Profile::Balanced
        );
        assert_eq!(
            effective_gaming(Profile::Gaming, false, false).0,
            Profile::Gaming
        );
    }

    #[test]
    fn saves_and_loads_master_profile() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("gaming-performance.toml");
        save_master(&path, Profile::Gaming).unwrap();
        assert_eq!(load_master(&path), Profile::Gaming);
    }

    #[test]
    fn apply_children_writes_drop_ins_and_does_not_ban_cpu1() {
        let directory = tempdir().unwrap();
        let root = directory.path();
        let paths = MasterApplyPaths {
            kargs_config: root.join("kargs.toml"),
            thp_config: root.join("thp.toml"),
            thp_dropin: root.join("thp.conf"),
            irq_config: root.join("irq.toml"),
            irq_dropin: root.join("irq.conf"),
            btrfs_config: root.join("btrfs.toml"),
            btrfs_dropin: root.join("btrfs.conf"),
            zswap_config: root.join("zswap.toml"),
            zswap_sysctl: root.join("zswap-sysctl.conf"),
            zswap_modprobe: root.join("zswap-modprobe.conf"),
            ananicy_config: root.join("ananicy.toml"),
            ananicy_rule: root.join("ananicy.json"),
        };
        let report = apply_children(true, &paths);
        let map: std::collections::BTreeMap<_, _> = report.into_iter().collect();
        assert_eq!(map.get("kargs").map(String::as_str), Some("ok"));
        assert_eq!(map.get("thp").map(String::as_str), Some("ok"));
        assert_eq!(map.get("btrfs").map(String::as_str), Some("ok"));
        assert_eq!(map.get("zswap").map(String::as_str), Some("ok"));
        assert_eq!(map.get("ananicy").map(String::as_str), Some("ok"));
        assert!(
            map.get("irq").is_some_and(|s| s.starts_with("error")),
            "irq must fail closed without isolated_cpus, got {:?}",
            map.get("irq")
        );
        assert!(!paths.irq_dropin.exists(), "must not write banned-cpus=1");
        assert!(paths.thp_dropin.exists());
        assert!(paths.zswap_sysctl.exists());
        let kargs = std::fs::read_to_string(&paths.kargs_config).unwrap();
        assert!(kargs.contains("gaming"));
        let report_off = apply_children(false, &paths);
        let map_off: std::collections::BTreeMap<_, _> = report_off.into_iter().collect();
        assert_eq!(map_off.get("thp").map(String::as_str), Some("ok"));
        assert!(!paths.thp_dropin.exists());
    }
}
