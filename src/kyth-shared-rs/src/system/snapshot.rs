//! Read-only snapshot/deployment timeline.
//!
//! Mirrors `kyth_shared.snapshot_timeline`: Snapper is preferred, Btrfs is a
//! filesystem-level fallback, and bootc deployments are appended from the
//! guarded status reader. No snapshot creation, deletion, or rollback is
//! performed here.

use serde::Serialize;
use serde_json::Value;
use std::collections::HashSet;
use std::time::Duration;

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
    Some((output.status.success(), String::from_utf8_lossy(&output.stdout).to_string()))
}

fn value_string(value: &Value) -> String {
    value.as_str().map_or_else(|| value.to_string(), str::to_string)
}

fn nested_string(value: &Value, path: &[&str]) -> Option<String> {
    let mut current = value;
    for key in path { current = current.get(*key)?; }
    current.as_str().map(str::to_string)
}

fn snapper_rows() -> Vec<SnapshotRow> {
    let Some((true, output)) = run_text("snapper", &["list", "--json"], Duration::from_secs(5)) else { return Vec::new(); };
    let Ok(data) = serde_json::from_str::<Value>(&output) else { return Vec::new(); };
    data.get("snapshots").and_then(Value::as_array).map(|snapshots| snapshots.iter().map(|snapshot| SnapshotRow {
        id: snapshot.get("number").map_or_else(String::new, value_string),
        timestamp: snapshot.get("date").map_or_else(String::new, value_string),
        row_type: "snapshot".to_string(),
        description: snapshot.get("description").map_or_else(String::new, value_string),
        healthy: None,
    }).collect()).unwrap_or_default()
}

fn btrfs_rows() -> Vec<SnapshotRow> {
    let Some((true, output)) = run_text("btrfs", &["subvolume", "list", "/"], Duration::from_secs(5)) else { return Vec::new(); };
    output.lines().take(20).map(|line| {
        let fields: Vec<&str> = line.split_whitespace().collect();
        SnapshotRow { id: fields.get(1).copied().unwrap_or_default().to_string(), timestamp: String::new(), row_type: "snapshot".to_string(), description: line.chars().take(80).collect(), healthy: None }
    }).collect()
}

fn bootc_rows() -> Vec<SnapshotRow> {
    let Some(data) = crate::system::bootc_query::fetch_status_data() else { return Vec::new(); };
    ["booted", "rollback", "staged"].into_iter().filter_map(|section| {
        let deployment = data.get("status")?.get(section)?;
        if deployment.is_null() { return None; }
        let digest = nested_string(deployment, &["image", "imageDigest"])
            .or_else(|| nested_string(deployment, &["imageDigest"]))
            .unwrap_or_default();
        let id = if digest.is_empty() { section.to_string() } else { digest.chars().take(12).collect() };
        Some(SnapshotRow { id, timestamp: String::new(), row_type: if section == "booted" { "deployment" } else { "rollback" }.to_string(), description: format!("{section}: {}", digest.chars().take(40).collect::<String>()), healthy: None })
    }).collect()
}

pub fn snapshot_timeline(limit: usize) -> Vec<SnapshotRow> {
    if limit == 0 { return Vec::new(); }
    let mut rows = snapper_rows();
    if rows.is_empty() { rows = btrfs_rows(); }
    rows.extend(bootc_rows());
    let mut seen = HashSet::new();
    rows.into_iter().filter(|row| seen.insert((row.id.clone(), row.row_type.clone()))).take(limit).collect()
}

pub fn snapshot_count() -> usize {
    // Keep the count independent from the presentation limit and avoid
    // querying bootc for a simple Repair-page badge.
    let rows = snapper_rows();
    if !rows.is_empty() { rows.len() } else { btrfs_rows().len() }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn nested_bootc_digest_is_read_without_mutation() {
        let data = json!({"image": {"imageDigest": "sha256:1234567890abcdef"}});
        assert_eq!(nested_string(&data, &["image", "imageDigest"]), Some("sha256:1234567890abcdef".into()));
    }

    #[test]
    fn zero_limit_is_empty() { assert!(snapshot_timeline(0).is_empty()); }

    #[test]
    fn row_serializes_type_as_wire_name() {
        let row = SnapshotRow { id: "1".into(), timestamp: String::new(), row_type: "snapshot".into(), description: "test".into(), healthy: None };
        assert_eq!(serde_json::to_value(row).unwrap()["type"], "snapshot");
    }
}
