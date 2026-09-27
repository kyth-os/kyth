//! Pure policy/config helpers for the privileged safe-upgrade workflow.
//!
//! The command boundary remains in the binary, while this module keeps the
//! rollout, manifest-fallback, digest, and fixed `/boot` argv policy reviewable
//! and testable without starting an upgrade or mounting anything.

use std::path::Path;

pub const DEFAULT_CONFIG_PATH: &str = "/etc/kyth/auto-update.toml";
pub const DEFAULT_ROLLOUT_RING: &str = "follow-image";

/// Rollout rings the updater accepts. Anything else in configuration is a
/// hard error: silently following the default ring would stage updates from
/// an unintended channel.
pub const VALID_ROLLOUT_RINGS: [&str; 4] = ["follow-image", "canary", "testing", "stable"];

/// Name of the environment variable that explicitly permits a staged image
/// older than the booted one (downgrade). Refusing downgrades is the
/// default; only an explicit opt-in bypasses the gate.
pub const ALLOW_DOWNGRADE_ENV: &str = "KYTH_ALLOW_DOWNGRADE";

/// Name of the environment variable that explicitly permits staging while
/// on battery power. A 30-minute download plus finalize must not start on
/// a draining battery by default — power loss mid-stage is the one failure
/// atomic updates cannot roll back from.
pub const ALLOW_BATTERY_ENV: &str = "KYTH_ALLOW_BATTERY_UPGRADE";

/// True when the machine is on AC power (or has no battery at all).
/// Desktops without a battery supply always pass; laptops require an
/// adapter reporting online. sysfs only, no D-Bus dependency.
pub fn on_ac_power_at(supply_dir: &Path) -> bool {
    let entries = std::fs::read_dir(supply_dir).map(|dir| dir.flatten().collect::<Vec<_>>());
    let entries = match entries {
        Ok(entries) if !entries.is_empty() => entries,
        // No power-supply class at all (VMs, containers): assume AC.
        _ => return true,
    };
    let has_battery = entries.iter().any(|entry| {
        entry.file_name().to_string_lossy().starts_with("BAT")
            || std::fs::read_to_string(entry.path().join("type"))
                .map(|kind| kind.trim().eq_ignore_ascii_case("battery"))
                .unwrap_or(false)
    });
    if !has_battery {
        return true;
    }
    entries.iter().any(|entry| {
        std::fs::read_to_string(entry.path().join("online"))
            .map(|state| state.trim() == "1")
            .unwrap_or(false)
    })
}

/// Refuse staging on battery unless explicitly overridden.
pub fn battery_gate_reason() -> Option<String> {
    if std::env::var(ALLOW_BATTERY_ENV).as_deref() == Ok("1") {
        return None;
    }
    if on_ac_power_at(Path::new("/sys/class/power_supply")) {
        return None;
    }
    Some(
        "Update blocked: running on battery power. Connect AC power or retry with KYTH_ALLOW_BATTERY_UPGRADE=1 to stage anyway."
            .to_string(),
    )
}

/// Strictly validate one configured ring value.
///
/// A missing value falls back to `last_known` (or the fail-safe default when
/// there is no last known ring). An explicitly configured but unknown value
/// is an error: the caller must keep the last known ring instead of staging
/// from an unintended channel.
pub fn validate_rollout_ring(configured: Option<&str>, last_known: &str) -> Result<String, String> {
    let Some(value) = configured.map(str::trim).filter(|value| !value.is_empty()) else {
        return Ok(if last_known.is_empty() {
            DEFAULT_ROLLOUT_RING.into()
        } else {
            last_known.into()
        });
    };
    if VALID_ROLLOUT_RINGS.contains(&value) {
        return Ok(value.into());
    }
    let keep = if last_known.is_empty() {
        DEFAULT_ROLLOUT_RING
    } else {
        last_known
    };
    Err(format!(
        "invalid rollout ring '{value}' (keeping last known ring '{keep}')"
    ))
}

/// Decode the rollout setting from captured TOML without performing I/O.
///
/// Strict: an explicitly configured unknown ring is an error and the caller
/// keeps `last_known`; only a missing key or malformed file falls back.
pub fn rollout_ring_from_toml(raw: &str, last_known: &str) -> Result<String, String> {
    let Ok(value) = raw.parse::<toml::Value>() else {
        return Ok(if last_known.is_empty() {
            DEFAULT_ROLLOUT_RING.into()
        } else {
            last_known.into()
        });
    };
    let section = value.get("auto_update").and_then(toml::Value::as_table);
    let Some(section) = section else {
        return Ok(if last_known.is_empty() {
            DEFAULT_ROLLOUT_RING.into()
        } else {
            last_known.into()
        });
    };
    match section.get("rollout_ring") {
        None => Ok(if last_known.is_empty() {
            DEFAULT_ROLLOUT_RING.into()
        } else {
            last_known.into()
        }),
        Some(toml::Value::String(value)) => validate_rollout_ring(Some(value), last_known),
        // Non-string TOML values can never name a valid ring; treat them as
        // unknown values (error), not as absent keys (fallback).
        Some(other) => validate_rollout_ring(Some(&other.to_string()), last_known),
    }
}

/// Read the configured rollout ring with strict validation.
///
/// Missing and unreadable files keep the last known ring (fail-safe default
/// when there is none). An explicitly configured unknown ring is an error;
/// the stored state keeps the last known ring because staging never runs.
pub fn load_rollout_ring(path: impl AsRef<Path>, last_known: &str) -> Result<String, String> {
    match std::fs::read_to_string(path) {
        Ok(raw) => rollout_ring_from_toml(&raw, last_known),
        Err(_) => Ok(if last_known.is_empty() {
            DEFAULT_ROLLOUT_RING.into()
        } else {
            last_known.into()
        }),
    }
}

/// The fixed remount attempts safe-upgrade makes, in order of preference.
/// Returning argv keeps execution and privilege decisions with the caller.
pub fn boot_remount_commands() -> [Vec<String>; 2] {
    [
        ["mount", "-o", "remount,bind,rw", "/boot"]
            .into_iter()
            .map(String::from)
            .collect(),
        ["mount", "-o", "remount,rw", "/boot"]
            .into_iter()
            .map(String::from)
            .collect(),
    ]
}

pub fn bind_sysroot_boot_command() -> Vec<String> {
    ["mount", "--bind", "/boot", "/sysroot/boot"]
        .into_iter()
        .map(String::from)
        .collect()
}

pub fn finalize_staged_command() -> Vec<String> {
    ["ostree", "admin", "finalize-staged"]
        .into_iter()
        .map(String::from)
        .collect()
}

/// Validate the digest bootc reports after staging an update.
///
/// A successful remote manifest probe gives us an immutable digest to compare
/// against. If that independent probe was unavailable, bootc's staged digest
/// is still authoritative for what it actually fetched, but a digest already
/// quarantined locally must remain blocked.
pub fn validate_staged_digest(
    remote_digest: Option<&str>,
    staged_digest: Option<&str>,
    quarantine_reason: Option<&str>,
) -> Result<String, String> {
    let staged = staged_digest
        .filter(|digest| !digest.is_empty())
        .ok_or_else(|| "bootc did not stage an image".to_string())?;
    if let Some(remote) = remote_digest {
        if staged != remote {
            return Err("bootc did not stage the requested image".to_string());
        }
    } else if let Some(reason) = quarantine_reason {
        return Err(format!("Update blocked: {reason}"));
    }
    Ok(staged.to_string())
}

/// Validate the state reported by bootc after an upgrade attempt.
///
/// `bootc upgrade` is the authoritative registry client for the mutating
/// path. A successful no-op has no staged digest, so it is represented as
/// `Ok(None)` when the booted digest is unchanged. Any other missing digest
/// is treated as a failed stage. A staged digest is always checked against
/// the local quarantine state before it is handed to the finalizer.
pub fn validate_post_upgrade_state(
    booted_before: Option<&str>,
    booted_after: Option<&str>,
    staged_after: Option<&str>,
    quarantine_reason: Option<&str>,
) -> Result<Option<String>, String> {
    if let Some(staged) = staged_after.filter(|digest| !digest.is_empty()) {
        return validate_staged_digest(None, Some(staged), quarantine_reason).map(Some);
    }
    if booted_before.is_some() && booted_after == booted_before {
        return Ok(None);
    }
    Err("bootc did not stage an image".into())
}

/// Compare two image version strings segment by segment.
///
/// Each dot/hyphen-separated segment compares numerically when both sides
/// are numeric, lexically otherwise. Missing segments compare less than
/// present ones, so `44` < `44.1`. Returns `None` when either side is empty.
pub fn compare_image_versions(booted: &str, staged: &str) -> Option<std::cmp::Ordering> {
    if booted.trim().is_empty() || staged.trim().is_empty() {
        return None;
    }
    let split = |version: &str| {
        version
            .split(['.', '-', '_', '+'])
            .filter(|segment| !segment.is_empty())
            .map(str::to_owned)
            .collect::<Vec<_>>()
    };
    let booted = split(booted);
    let staged = split(staged);
    for pair in booted.iter().zip(staged.iter()) {
        let ordering = match (pair.0.parse::<u64>(), pair.1.parse::<u64>()) {
            (Ok(left), Ok(right)) => left.cmp(&right),
            _ => pair.0.cmp(pair.1),
        };
        if ordering != std::cmp::Ordering::Equal {
            return Some(ordering);
        }
    }
    Some(booted.len().cmp(&staged.len()))
}

/// Whether an explicit downgrade opt-in is present.
///
/// The `auto_update.allow_downgrade` TOML key or a truthy
/// `KYTH_ALLOW_DOWNGRADE` environment value (`1`/`true`/`yes`) permits
/// staging an image older than the booted one. Anything else refuses.
pub fn allow_downgrade_from_toml(raw: &str) -> bool {
    if let Ok(value) = raw.parse::<toml::Value>() {
        if let Some(section) = value.get("auto_update").and_then(toml::Value::as_table) {
            if section
                .get("allow_downgrade")
                .and_then(toml::Value::as_bool)
                == Some(true)
            {
                return true;
            }
        }
    }
    matches!(
        std::env::var(ALLOW_DOWNGRADE_ENV)
            .unwrap_or_default()
            .trim()
            .to_ascii_lowercase()
            .as_str(),
        "1" | "true" | "yes"
    )
}

/// Refuse a staged image older than the recorded booted release.
///
/// The caller records the booted version and digest *before* staging and the
/// staged version and digest *after*; this gate compares them. An identical
/// digest is always accepted (same image, not a downgrade). A staged version
/// older than the booted one is refused unless `allow_downgrade` carries an
/// explicit opt-in. Missing versions cannot be ordered, so they pass — the
/// digest and quarantine gates above remain authoritative.
pub fn validate_not_downgrade(
    booted_version: Option<&str>,
    booted_digest: Option<&str>,
    staged_version: Option<&str>,
    staged_digest: Option<&str>,
    allow_downgrade: bool,
) -> Result<(), String> {
    if let (Some(booted), Some(staged)) = (booted_digest, staged_digest) {
        if !booted.is_empty() && booted == staged {
            return Ok(());
        }
    }
    let (Some(booted), Some(staged)) = (booted_version, staged_version) else {
        return Ok(());
    };
    match compare_image_versions(booted, staged) {
        Some(std::cmp::Ordering::Greater) if !allow_downgrade => Err(format!(
            "refusing staged downgrade from version '{booted}' to '{staged}'; \
             set auto_update.allow_downgrade = true to permit it"
        )),
        _ => Ok(()),
    }
}

/// Convert a registry check into the digest gate used by safe-upgrade.
///
/// A local status failure remains fail-closed. A remote probe failure is
/// explicitly represented as `Ok(None)` so bootc can be the authoritative
/// fetcher for the update.
pub fn remote_digest_for_safe_upgrade(
    state: &str,
    detail: &str,
    remote_probe_failed: bool,
    manifest_raw: &[u8],
) -> Result<Option<String>, String> {
    if state == "error" && !remote_probe_failed {
        return Err(detail.to_string());
    }
    if remote_probe_failed {
        return Ok(None);
    }
    crate::system::registry::remote_digest_and_timestamp(manifest_raw)
        .0
        .map(Some)
        .ok_or_else(|| "Could not resolve the remote image digest; update not staged".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    fn supply_fixture(entries: &[(&str, &str)]) -> tempfile::TempDir {
        let dir = tempdir().expect("tempdir");
        for (name, kind) in entries {
            let supply = dir.path().join(name);
            fs::create_dir(&supply).expect("supply dir");
            fs::write(supply.join("type"), kind).expect("type file");
        }
        dir
    }

    #[test]
    fn ac_gate_passes_desktops_and_plugged_laptops() {
        // No power-supply class (VM/container): assume AC.
        assert!(on_ac_power_at(Path::new("/nonexistent-kyth-test")));
        // Desktop with only an AC adapter: AC.
        let desktop = supply_fixture(&[("AC", "Mains")]);
        fs::write(desktop.path().join("AC").join("online"), "1").expect("online");
        assert!(on_ac_power_at(desktop.path()));
        // Laptop on adapter: AC.
        let laptop = supply_fixture(&[("AC", "Mains"), ("BAT0", "Battery")]);
        fs::write(laptop.path().join("AC").join("online"), "1").expect("online");
        assert!(on_ac_power_at(laptop.path()));
        // Laptop unplugged: battery.
        let unplugged = supply_fixture(&[("AC", "Mains"), ("BAT0", "Battery")]);
        fs::write(unplugged.path().join("AC").join("online"), "0").expect("online");
        assert!(!on_ac_power_at(unplugged.path()));
    }

    #[test]
    fn parses_rollout_ring_and_strict_unknowns() {
        // Known rings resolve.
        assert_eq!(
            rollout_ring_from_toml("[auto_update]\nrollout_ring = \"testing\"\n", ""),
            Ok("testing".into())
        );
        // Missing keys and malformed files keep the last known ring.
        assert_eq!(
            rollout_ring_from_toml("[other]\nvalue = 1\n", "stable"),
            Ok("stable".into())
        );
        assert_eq!(
            rollout_ring_from_toml("not toml", ""),
            Ok(DEFAULT_ROLLOUT_RING.into())
        );
        // Unknown explicit values error and name the ring that is kept.
        assert_eq!(
            rollout_ring_from_toml("[auto_update]\nrollout_ring = \"nightly\"\n", "testing"),
            Err("invalid rollout ring 'nightly' (keeping last known ring 'testing')".into())
        );
        // Non-string TOML values are unknown values, not absent keys.
        assert!(rollout_ring_from_toml("[auto_update]\nrollout_ring = true\n", "stable").is_err());
        assert!(rollout_ring_from_toml("[auto_update]\nrollout_ring = 7\n", "").is_err());
    }

    #[test]
    fn loads_rollout_ring_from_an_explicit_path() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("auto-update.toml");
        fs::write(&path, "[auto_update]\nrollout_ring = \"canary\"\n").unwrap();
        assert_eq!(load_rollout_ring(&path, ""), Ok("canary".into()));
        // Unreadable files keep the last known ring.
        assert_eq!(
            load_rollout_ring(directory.path().join("missing.toml"), "stable"),
            Ok("stable".into())
        );
        assert_eq!(
            load_rollout_ring(directory.path().join("missing.toml"), ""),
            Ok(DEFAULT_ROLLOUT_RING.into())
        );
        // Unknown configured values error instead of silently following.
        fs::write(&path, "[auto_update]\nrollout_ring = \"beta\"\n").unwrap();
        assert_eq!(
            load_rollout_ring(&path, "canary"),
            Err("invalid rollout ring 'beta' (keeping last known ring 'canary')".into())
        );
    }

    #[test]
    fn projects_only_the_fixed_upgrade_boundary_commands() {
        assert_eq!(
            boot_remount_commands()[0],
            vec!["mount", "-o", "remount,bind,rw", "/boot"]
        );
        assert_eq!(
            boot_remount_commands()[1],
            vec!["mount", "-o", "remount,rw", "/boot"]
        );
        assert_eq!(
            bind_sysroot_boot_command(),
            vec!["mount", "--bind", "/boot", "/sysroot/boot"]
        );
        assert_eq!(
            finalize_staged_command(),
            vec!["ostree", "admin", "finalize-staged"]
        );
    }

    #[test]
    fn staged_digest_must_match_a_successful_remote_probe() {
        assert_eq!(
            validate_staged_digest(Some("sha256:remote"), Some("sha256:remote"), None),
            Ok("sha256:remote".into())
        );
        assert_eq!(
            validate_staged_digest(Some("sha256:remote"), Some("sha256:other"), None),
            Err("bootc did not stage the requested image".into())
        );
    }

    #[test]
    fn bootc_digest_is_accepted_when_remote_probe_is_unavailable() {
        assert_eq!(
            validate_staged_digest(None, Some("sha256:bootc"), None),
            Ok("sha256:bootc".into())
        );
    }

    #[test]
    fn degraded_path_still_blocks_a_locally_quarantined_digest() {
        assert_eq!(
            validate_staged_digest(None, Some("sha256:bad"), Some("sha256:bad is quarantined")),
            Err("Update blocked: sha256:bad is quarantined".into())
        );
    }

    #[test]
    fn staging_without_a_digest_is_never_successful() {
        assert_eq!(
            validate_staged_digest(None, None, None),
            Err("bootc did not stage an image".into())
        );
    }

    #[test]
    fn post_upgrade_accepts_bootc_staged_digest() {
        assert_eq!(
            validate_post_upgrade_state(
                Some("sha256:old"),
                Some("sha256:old"),
                Some("sha256:new"),
                None,
            ),
            Ok(Some("sha256:new".into()))
        );
    }

    #[test]
    fn post_upgrade_accepts_a_successful_noop() {
        assert_eq!(
            validate_post_upgrade_state(Some("sha256:same"), Some("sha256:same"), None, None,),
            Ok(None)
        );
    }

    #[test]
    fn post_upgrade_rejects_missing_digests_and_quarantine() {
        assert_eq!(
            validate_post_upgrade_state(None, None, None, None),
            Err("bootc did not stage an image".into())
        );
        assert_eq!(
            validate_post_upgrade_state(
                Some("sha256:old"),
                Some("sha256:old"),
                Some("sha256:bad"),
                Some("sha256:bad is quarantined"),
            ),
            Err("Update blocked: sha256:bad is quarantined".into())
        );
    }

    #[test]
    fn remote_probe_failure_is_degraded_but_local_status_failure_is_not() {
        assert_eq!(
            remote_digest_for_safe_upgrade(
                "error",
                "Timed out checking ghcr.io/kyth-os/kyth:testing.",
                true,
                &[]
            ),
            Ok(None)
        );
        assert_eq!(
            remote_digest_for_safe_upgrade(
                "error",
                "Could not read the current booted image digest.",
                false,
                &[]
            ),
            Err("Could not read the current booted image digest.".into())
        );
    }

    #[test]
    fn staged_older_than_booted_is_refused_without_explicit_opt_in() {
        // Older staged version without opt-in is refused.
        assert!(validate_not_downgrade(
            Some("44.20260801.0"),
            Some("sha256:booted"),
            Some("43.20260701.0"),
            Some("sha256:staged"),
            false,
        )
        .is_err());
        // Same comparison passes with the explicit allow-downgrade flag.
        assert_eq!(
            validate_not_downgrade(
                Some("44.20260801.0"),
                Some("sha256:booted"),
                Some("43.20260701.0"),
                Some("sha256:staged"),
                true,
            ),
            Ok(())
        );
        // Newer staged versions always pass; identical digests always pass.
        assert_eq!(
            validate_not_downgrade(
                Some("43"),
                Some("sha256:a"),
                Some("44.1"),
                Some("sha256:b"),
                false,
            ),
            Ok(())
        );
        assert_eq!(
            validate_not_downgrade(
                Some("44"),
                Some("sha256:same"),
                Some("43"),
                Some("sha256:same"),
                false,
            ),
            Ok(())
        );
        // Missing versions cannot be ordered, so they pass through to the
        // digest and quarantine gates.
        assert_eq!(
            validate_not_downgrade(None, None, None, None, false),
            Ok(())
        );
        // Numeric segments compare numerically, not lexically: 9 < 10.
        assert!(validate_not_downgrade(
            Some("44.10"),
            Some("sha256:a"),
            Some("44.9"),
            Some("sha256:b"),
            false,
        )
        .is_err());
        assert_eq!(
            compare_image_versions("44", "44.1"),
            Some(std::cmp::Ordering::Less)
        );
    }

    #[test]
    fn downgrade_opt_in_requires_config_or_environment() {
        assert!(allow_downgrade_from_toml(
            "[auto_update]\nallow_downgrade = true\n"
        ));
        assert!(!allow_downgrade_from_toml(
            "[auto_update]\nrollout_ring = \"stable\"\n"
        ));
        assert!(!allow_downgrade_from_toml("not toml"));
    }
}
