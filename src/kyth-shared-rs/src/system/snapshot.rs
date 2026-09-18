//! Read-only snapshot/deployment timeline plus snapshot-operation planning.
//!
//! The timeline itself mirrors `kyth_shared.snapshot_timeline`: Snapper is
//! preferred, Btrfs is a filesystem-level fallback, and bootc deployments
//! are appended from the guarded status reader. No snapshot creation,
//! deletion, or rollback is performed here.
//!
//! The planning helpers below (`pre_snapshot_argv`, `post_snapshot_argv`,
//! [`snapshot_then_send_plan`]) are pure argv builders for the operations
//! the image performs around updates/polish and USB offload. Only the
//! `*_bin.rs` entry points execute them.
//!
//! Snapshot storage budget: snapper timeline snapshots plus the read-only
//! staging snapshots used for USB send share one btrfs quota on `/home`,
//! capped at [`HOME_QUOTA_LIMIT_PCT`]% (see
//! `build_files/scripts/branding/46-snapshot-autoclean.sh`). Timeline
//! pruning (`snapper` `TIMELINE_LIMIT_*`) keeps steady-state usage far below
//! the cap; the headroom exists so a pre-update snapshot never fails for
//! lack of quota while an offload staging snapshot exists.

use serde::Serialize;
use serde_json::Value;
use std::collections::HashSet;
use std::time::Duration;

/// Share of `/home` that snapshots (timeline + USB-send staging) may occupy
/// before the qgroup cap stops new snapshots. Raised from the original 20%
/// so a pre-update snapshot plus one in-flight USB offload staging snapshot
/// fit together on small (256 GiB) disks without tripping the limiter.
pub const HOME_QUOTA_LIMIT_PCT: u32 = 35;

/// Snapper timeline retention for the `root` config: hourly/daily caps keep
/// the steady-state snapshot count bounded under the quota above.
pub const SNAPPER_ROOT_TIMELINE_LIMITS: &[(&str, &str)] = &[
    ("TIMELINE_CREATE", "yes"),
    ("TIMELINE_LIMIT_HOURLY", "5"),
    ("TIMELINE_LIMIT_DAILY", "7"),
];

/// Snapper timeline retention for the `home` config. Home churns faster
/// than `/`, so the hourly window is wider but the daily cap matches root
/// to hold total usage under the shared quota.
pub const SNAPPER_HOME_TIMELINE_LIMITS: &[(&str, &str)] = &[
    ("TIMELINE_CREATE", "yes"),
    ("TIMELINE_LIMIT_HOURLY", "8"),
    ("TIMELINE_LIMIT_DAILY", "7"),
];

/// `snapper -c <config> create-config <path>` argv (idempotent; snapper
/// refuses when the config already exists, which callers treat as success).
pub fn snapper_create_config_argv(config: &str, path: &str) -> Vec<String> {
    vec![
        "snapper".to_string(),
        "-c".to_string(),
        config.to_string(),
        "create-config".to_string(),
        path.to_string(),
    ]
}

/// `snapper -c <config> set-config K=V …` argv for the timeline limits.
pub fn snapper_set_config_argv(config: &str, limits: &[(&str, &str)]) -> Vec<String> {
    let mut argv = vec![
        "snapper".to_string(),
        "-c".to_string(),
        config.to_string(),
        "set-config".to_string(),
    ];
    argv.extend(limits.iter().map(|(key, value)| format!("{key}={value}")));
    argv
}

/// Pre-update/pre-polish snapshot: `snapper -c <config> create --type pre
/// --description <description> --print-number`. The printed number feeds
/// [`post_snapshot_argv`].
pub fn pre_snapshot_argv(config: &str, description: &str) -> Vec<String> {
    vec![
        "snapper".to_string(),
        "-c".to_string(),
        config.to_string(),
        "create".to_string(),
        "--type".to_string(),
        "pre".to_string(),
        "--description".to_string(),
        description.to_string(),
        "--print-number".to_string(),
    ]
}

/// Post-update/post-polish snapshot paired with a pre snapshot number.
pub fn post_snapshot_argv(config: &str, pre_number: u64, description: &str) -> Vec<String> {
    vec![
        "snapper".to_string(),
        "-c".to_string(),
        config.to_string(),
        "create".to_string(),
        "--type".to_string(),
        "post".to_string(),
        "--pre-number".to_string(),
        pre_number.to_string(),
        "--description".to_string(),
        description.to_string(),
    ]
}

/// Snapshot-then-send USB offload plan.
///
/// `btrfs send` requires a read-only snapshot — it cannot stream a live,
/// mounted subvolume. The old launcher sent `/home` directly, which btrfs
/// rejects (or worse, streams an inconsistent view). The safe order is:
/// freeze a read-only snapshot of `/home` under `staging_dir`, send the
/// *snapshot* to the USB target, then delete the staging snapshot.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SnapshotSendPlan {
    /// Read-only staging snapshot path, e.g. `/home/.snapshots/kyth-send`.
    pub snapshot_path: String,
    /// `btrfs subvolume snapshot -r /home <snapshot_path>`
    pub snapshot_argv: Vec<String>,
    /// `btrfs send <snapshot_path>` streamed at `usb_target` (never the live
    /// subvolume: `btrfs send` requires a read-only snapshot).
    pub send_argv: Vec<String>,
    /// `btrfs subvolume delete <snapshot_path>` (cleanup after send).
    pub cleanup_argv: Vec<String>,
}

pub fn snapshot_then_send_plan(
    home: &str,
    staging_name: &str,
    usb_target: &str,
) -> SnapshotSendPlan {
    let snapshot_path = format!("{}/.snapshots/{staging_name}", home.trim_end_matches('/'));
    SnapshotSendPlan {
        snapshot_argv: vec![
            "btrfs".to_string(),
            "subvolume".to_string(),
            "snapshot".to_string(),
            "-r".to_string(),
            home.to_string(),
            format!("{}/.snapshots/{staging_name}", home.trim_end_matches('/')),
        ],
        send_argv: vec![
            "btrfs".to_string(),
            "send".to_string(),
            format!("{}/.snapshots/{staging_name}", home.trim_end_matches('/')),
            usb_target.to_string(),
        ],
        cleanup_argv: vec![
            "btrfs".to_string(),
            "subvolume".to_string(),
            "delete".to_string(),
            format!("{}/.snapshots/{staging_name}", home.trim_end_matches('/')),
        ],
        snapshot_path,
    }
}

/// `statvfs` filesystem magic for Btrfs. A `btrfs send` stream can only land
/// on a Btrfs volume (`btrfs receive`); streaming into an exfat/NTFS stick
/// or the wrong directory silently produces no usable offload.
pub const BTRFS_MAGIC: i64 = 0x9123_683E;

/// Minimum free bytes required on a USB send target before streaming.
/// A full-home send that runs out of space mid-stream leaves a truncated,
/// unrestorable receive directory — fail closed instead.
pub const MIN_SEND_TARGET_FREE_BYTES: u64 = 1024 * 1024 * 1024;

/// Pure gate for a USB `btrfs send` target, over an already-observed
/// filesystem magic and free-byte count so it is unit-testable without
/// touching live mounts. Callers observe both via `statfs`.
pub fn validate_send_target(target: &str, fs_magic: i64, free_bytes: u64) -> Result<(), String> {
    if fs_magic != BTRFS_MAGIC {
        return Err(format!(
            "btrfs send target {target:?} is not a Btrfs filesystem (magic {fs_magic:#x}); \
the send stream cannot be received there. Format the stick as Btrfs or pick another target."
        ));
    }
    if free_bytes < MIN_SEND_TARGET_FREE_BYTES {
        return Err(format!(
            "btrfs send target {target:?} has only {free_bytes} bytes free \
(need at least {MIN_SEND_TARGET_FREE_BYTES}); refusing a send that would truncate mid-stream."
        ));
    }
    Ok(())
}

/// Observe `(fs_type_magic, free_bytes)` for `path` via `statfs`.
pub fn statvfs_usage(path: &std::path::Path) -> Option<(i64, u64)> {
    use std::ffi::CString;
    use std::os::unix::ffi::OsStrExt;
    let cpath = CString::new(path.as_os_str().as_bytes()).ok()?;
    let mut stat: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::statfs(cpath.as_ptr(), &mut stat) } != 0 {
        return None;
    }
    Some((
        i64::from(stat.f_type),
        stat.f_bavail.saturating_mul(stat.f_bsize.max(0) as u64),
    ))
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct SnapshotRow {
    pub id: String,
    pub timestamp: String,
    #[serde(rename = "type")]
    pub row_type: String,
    pub description: String,
    pub healthy: Option<bool>,
}

fn run_text(program: &str, args: &[&str], timeout: Duration) -> Option<(bool, String)> {
    let mut argv = vec![program.to_string()];
    argv.extend(args.iter().map(|arg| (*arg).to_string()));
    let output = super::process::run_bounded(&argv, timeout).ok()?;
    Some((
        output.status.success(),
        String::from_utf8_lossy(&output.stdout).to_string(),
    ))
}

fn value_string(value: &Value) -> String {
    value
        .as_str()
        .map_or_else(|| value.to_string(), str::to_string)
}

fn nested_string(value: &Value, path: &[&str]) -> Option<String> {
    let mut current = value;
    for key in path {
        current = current.get(*key)?;
    }
    current.as_str().map(str::to_string)
}

/// Parse a captured `snapper list --json` response without invoking Snapper.
pub fn parse_snapper_rows(output: &str) -> Vec<SnapshotRow> {
    let Ok(data) = serde_json::from_str::<Value>(output) else {
        return Vec::new();
    };
    data.get("snapshots")
        .and_then(Value::as_array)
        .map(|snapshots| {
            snapshots
                .iter()
                .map(|snapshot| SnapshotRow {
                    id: snapshot
                        .get("number")
                        .map_or_else(String::new, value_string),
                    timestamp: snapshot.get("date").map_or_else(String::new, value_string),
                    row_type: "snapshot".to_string(),
                    description: snapshot
                        .get("description")
                        .map_or_else(String::new, value_string),
                    healthy: None,
                })
                .collect()
        })
        .unwrap_or_default()
}

/// Parse a captured `btrfs subvolume list` response without touching Btrfs.
pub fn parse_btrfs_rows(output: &str) -> Vec<SnapshotRow> {
    output
        .lines()
        .take(20)
        .map(|line| {
            let fields: Vec<&str> = line.split_whitespace().collect();
            SnapshotRow {
                id: fields.get(1).copied().unwrap_or_default().to_string(),
                timestamp: String::new(),
                row_type: "snapshot".to_string(),
                description: line.chars().take(80).collect(),
                healthy: None,
            }
        })
        .collect()
}

/// Parse bootc deployment entries from an already-decoded status document.
pub fn parse_bootc_rows(data: &Value) -> Vec<SnapshotRow> {
    ["booted", "rollback", "staged"]
        .into_iter()
        .filter_map(|section| {
            let deployment = data.get("status")?.get(section)?;
            if deployment.is_null() {
                return None;
            }
            let digest = nested_string(deployment, &["image", "imageDigest"])
                .or_else(|| nested_string(deployment, &["imageDigest"]))
                .unwrap_or_default();
            let id = if digest.is_empty() {
                section.to_string()
            } else {
                digest.chars().take(12).collect()
            };
            Some(SnapshotRow {
                id,
                timestamp: String::new(),
                row_type: if section == "booted" {
                    "deployment"
                } else {
                    "rollback"
                }
                .to_string(),
                description: format!("{section}: {}", digest.chars().take(40).collect::<String>()),
                healthy: None,
            })
        })
        .collect()
}

fn snapper_rows() -> Vec<SnapshotRow> {
    let Some((true, output)) = run_text("snapper", &["list", "--json"], Duration::from_secs(5))
    else {
        return Vec::new();
    };
    parse_snapper_rows(&output)
}

fn btrfs_rows() -> Vec<SnapshotRow> {
    let Some((true, output)) =
        run_text("btrfs", &["subvolume", "list", "/"], Duration::from_secs(5))
    else {
        return Vec::new();
    };
    parse_btrfs_rows(&output)
}

fn bootc_rows() -> Vec<SnapshotRow> {
    let Some(data) = crate::system::bootc_query::fetch_status_data() else {
        return Vec::new();
    };
    parse_bootc_rows(&data)
}

pub fn snapshot_timeline(limit: usize) -> Vec<SnapshotRow> {
    if limit == 0 {
        return Vec::new();
    }
    let mut rows = snapper_rows();
    if rows.is_empty() {
        rows = btrfs_rows();
    }
    rows.extend(bootc_rows());
    let mut seen = HashSet::new();
    rows.into_iter()
        .filter(|row| seen.insert((row.id.clone(), row.row_type.clone())))
        .take(limit)
        .collect()
}

/// Serialize a captured timeline using the same wire shape as the Python
/// `snapshot_timeline_json` helper. This projection is intentionally separate
/// from collection so callers can render supplied rows without running tools.
pub fn snapshot_rows_json(rows: &[SnapshotRow]) -> String {
    serde_json::to_string_pretty(rows).unwrap_or_else(|_| "[]".to_string())
}

pub fn snapshot_timeline_json(limit: usize) -> String {
    snapshot_rows_json(&snapshot_timeline(limit))
}

pub fn snapshot_count() -> usize {
    // Keep the count independent from the presentation limit and avoid
    // querying bootc for a simple Repair-page badge.
    let rows = snapper_rows();
    if !rows.is_empty() {
        rows.len()
    } else {
        btrfs_rows().len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn nested_bootc_digest_is_read_without_mutation() {
        let data = json!({"image": {"imageDigest": "sha256:1234567890abcdef"}});
        assert_eq!(
            nested_string(&data, &["image", "imageDigest"]),
            Some("sha256:1234567890abcdef".into())
        );
    }

    #[test]
    fn zero_limit_is_empty() {
        assert!(snapshot_timeline(0).is_empty());
    }

    #[test]
    fn row_serializes_type_as_wire_name() {
        let row = SnapshotRow {
            id: "1".into(),
            timestamp: String::new(),
            row_type: "snapshot".into(),
            description: "test".into(),
            healthy: None,
        };
        assert_eq!(serde_json::to_value(row).unwrap()["type"], "snapshot");
    }

    #[test]
    fn serializes_supplied_rows_with_python_wire_keys() {
        let rows = [SnapshotRow {
            id: "7".into(),
            timestamp: "today".into(),
            row_type: "snapshot".into(),
            description: "before update".into(),
            healthy: None,
        }];
        let encoded = snapshot_rows_json(&rows);
        assert!(encoded.contains("\"type\": \"snapshot\""));
        assert!(!encoded.contains("row_type"));
    }

    #[test]
    fn parses_snapper_rows_without_running_snapper() {
        let rows = parse_snapper_rows(
            r#"{"snapshots":[{"number":7,"date":"2026-08-30","description":"before update"}]}"#,
        );
        assert_eq!(
            rows,
            vec![SnapshotRow {
                id: "7".into(),
                timestamp: "2026-08-30".into(),
                row_type: "snapshot".into(),
                description: "before update".into(),
                healthy: None
            }]
        );
        assert!(parse_snapper_rows("not json").is_empty());
    }

    #[test]
    fn parses_btrfs_rows_with_a_bounded_description() {
        let rows = parse_btrfs_rows("ID 42 gen 9 top level 5 path @root\nshort");
        assert_eq!(rows[0].id, "42");
        assert_eq!(rows[1].id, "");
        assert!(rows[0].description.len() <= 80);
    }

    #[test]
    fn parses_bootc_deployments_in_stable_order() {
        let rows = parse_bootc_rows(&json!({"status": {
            "booted": {"image": {"imageDigest": "sha256:booted"}},
            "rollback": {"imageDigest": "sha256:rollback"},
            "staged": null
        }}));
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].row_type, "deployment");
        assert_eq!(rows[1].row_type, "rollback");
        assert_eq!(rows[1].id, "sha256:rollb");
    }

    #[test]
    fn send_target_requires_btrfs_and_headroom() {
        // exFAT stick (0x2011b958): refused — the stream could never land.
        assert!(validate_send_target("/run/media/u/STICK", 0x2011_b958, u64::MAX).is_err());
        // Btrfs but nearly full: refused — a truncated stream is unrestorable.
        assert!(validate_send_target("/run/media/u/BACKUP", BTRFS_MAGIC, 0).is_err());
        assert!(validate_send_target(
            "/run/media/u/BACKUP",
            BTRFS_MAGIC,
            MIN_SEND_TARGET_FREE_BYTES - 1
        )
        .is_err());
        // Btrfs with headroom: accepted.
        assert!(validate_send_target(
            "/run/media/u/BACKUP",
            BTRFS_MAGIC,
            MIN_SEND_TARGET_FREE_BYTES
        )
        .is_ok());
    }

    #[test]
    fn quota_cap_covers_timeline_plus_one_staging_snapshot() {
        // Documented budget: the cap must leave room for a pre-update
        // snapshot alongside one in-flight USB offload staging snapshot.
        // 35% of even a 256 GiB disk dwarfs both; anything at or below the
        // old 20% risks tripping the limiter mid-update on small disks.
        assert!(HOME_QUOTA_LIMIT_PCT > 20);
        assert_eq!(HOME_QUOTA_LIMIT_PCT, 35);
    }

    #[test]
    fn pre_and_post_snapshots_pair_by_number() {
        let pre = pre_snapshot_argv("root", "before kyth update");
        assert_eq!(
            pre,
            vec![
                "snapper",
                "-c",
                "root",
                "create",
                "--type",
                "pre",
                "--description",
                "before kyth update",
                "--print-number"
            ]
        );
        let post = post_snapshot_argv("root", 42, "after kyth update");
        assert!(post.windows(2).any(|pair| pair == ["--pre-number", "42"]));
        assert!(post.windows(2).any(|pair| pair == ["--type", "post"]));
        let home_cfg = snapper_set_config_argv("home", SNAPPER_HOME_TIMELINE_LIMITS);
        assert!(home_cfg.iter().any(|arg| arg == "TIMELINE_LIMIT_HOURLY=8"));
        assert!(home_cfg.iter().any(|arg| arg == "TIMELINE_LIMIT_DAILY=7"));
        let root_cfg = snapper_set_config_argv("root", SNAPPER_ROOT_TIMELINE_LIMITS);
        assert!(root_cfg.iter().any(|arg| arg == "TIMELINE_LIMIT_HOURLY=5"));
        assert_eq!(
            snapper_create_config_argv("home", "/home"),
            vec!["snapper", "-c", "home", "create-config", "/home"]
        );
    }

    #[test]
    fn usb_offload_sends_a_snapshot_never_the_live_subvolume() {
        let plan =
            snapshot_then_send_plan("/home", "kyth-send", "/run/media/alice/BACKUP/home.btrfs");
        assert_eq!(plan.snapshot_path, "/home/.snapshots/kyth-send");
        // Freeze first: read-only snapshot of /home.
        assert_eq!(
            &plan.snapshot_argv[..4],
            ["btrfs", "subvolume", "snapshot", "-r"]
        );
        assert_eq!(plan.snapshot_argv[4], "/home");
        // Send the snapshot — the live subvolume must not appear as the
        // send source (btrfs send requires a read-only snapshot).
        assert!(plan.send_argv.iter().any(|arg| arg == "send"));
        assert!(plan.send_argv.iter().any(|arg| arg == &plan.snapshot_path));
        assert!(!plan.send_argv.iter().any(|arg| arg == "/home"));
        // Cleanup removes the staging snapshot afterwards.
        assert_eq!(plan.cleanup_argv[..3], ["btrfs", "subvolume", "delete"]);
        assert_eq!(plan.cleanup_argv[3], plan.snapshot_path);
    }
}
