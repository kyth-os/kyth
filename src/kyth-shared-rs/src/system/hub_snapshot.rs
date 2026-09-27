//! Typed, read-only summary for native Hub refreshes.
//!
//! This composes existing cached/read-only Rust views.  It deliberately does
//! not refresh probes, invoke commands, or execute actions.

use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct MoveInReadiness {
    pub ntfs_drives: usize,
    pub cloud_providers: usize,
    pub smb_shares: i64,
    pub vpn_connected: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct SoftwareReadiness {
    pub installed_flatpaks: usize,
    pub available_flatpak_updates: i64,
    pub appimages: usize,
    pub starter_packs: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct GamingReadiness {
    pub installed_launchers: usize,
    pub library_entries: usize,
    pub session_count: usize,
    pub median_fps: Option<f64>,
    pub median_p1_low_fps: Option<f64>,
    pub total_duration_s: f64,
    pub stutter_count: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct HubSnapshot {
    pub doctor_score: u8,
    pub doctor_suggestions: usize,
    pub update_state: String,
    pub update_staged: bool,
    pub guardian_pending: usize,
    pub move_in: MoveInReadiness,
    pub software: SoftwareReadiness,
    pub gaming: GamingReadiness,
}

impl HubSnapshot {
    /// Compose the existing smoke qualification with the locally persisted
    /// gaming telemetry summary.  Collection stays with the caller; this only
    /// projects already-available records into the shared report format.
    pub fn qualification_report(
        &self,
        generated_at: impl Into<String>,
        identity: std::collections::BTreeMap<String, String>,
        smoke: &crate::system::smoke_check::Report,
    ) -> crate::system::qualification::QualificationReport {
        let mut report =
            crate::system::qualification::from_smoke_report(generated_at, identity, smoke);
        report
            .metrics
            .extend(gaming_qualification_metrics(&self.gaming));
        report
    }
}

fn median(mut values: Vec<f64>) -> Option<f64> {
    values.retain(|value| value.is_finite());
    values.sort_by(f64::total_cmp);
    let mid = values.len() / 2;
    match values.len() {
        0 => None,
        count if count % 2 == 1 => Some(values[mid]),
        _ => Some((values[mid - 1] + values[mid]) / 2.0),
    }
}

pub fn move_in_readiness_from(
    network: Option<&serde_json::Value>,
    ntfs_drives: usize,
) -> MoveInReadiness {
    let cloud_providers = network
        .and_then(|value| value.get("cloud_providers"))
        .and_then(serde_json::Value::as_array)
        .map_or(0, Vec::len);
    let smb_shares = network
        .and_then(|value| value.get("smb_mounts"))
        .and_then(serde_json::Value::as_i64)
        .unwrap_or(0);
    let vpn_connected = network
        .and_then(|value| value.get("vpn_connected"))
        .and_then(serde_json::Value::as_bool)
        .unwrap_or(false);
    MoveInReadiness {
        ntfs_drives,
        cloud_providers,
        smb_shares,
        vpn_connected,
    }
}

pub fn gaming_readiness_from(
    launchers: &[crate::system::gaming_library::LauncherEntry],
    sessions: &[crate::system::telemetry::SessionRow],
) -> GamingReadiness {
    GamingReadiness {
        installed_launchers: launchers
            .iter()
            .filter(|launcher| launcher.installed)
            .count(),
        library_entries: launchers
            .iter()
            .filter_map(|launcher| launcher.library_count)
            .sum(),
        session_count: sessions.len(),
        median_fps: median(
            sessions
                .iter()
                .filter_map(|session| session.avg_fps)
                .collect(),
        ),
        median_p1_low_fps: median(
            sessions
                .iter()
                .filter_map(|session| session.p1_low_fps)
                .collect(),
        ),
        total_duration_s: sessions
            .iter()
            .filter_map(|session| session.duration_s)
            .sum(),
        stutter_count: sessions.iter().map(|session| session.stutter_count).sum(),
    }
}

pub fn gaming_qualification_metrics(
    readiness: &GamingReadiness,
) -> Vec<crate::system::qualification::QualificationMetric> {
    let mut metrics = Vec::new();
    if let Some(value) = readiness.median_fps {
        metrics.push(
            crate::system::qualification::QualificationMetric::new(
                "gaming.avg_fps",
                value,
                "fps",
                "higher",
                "system",
            )
            .expect("fixed metric is valid"),
        );
    }
    if let Some(value) = readiness.median_p1_low_fps {
        metrics.push(
            crate::system::qualification::QualificationMetric::new(
                "gaming.p1_low_fps",
                value,
                "fps",
                "higher",
                "system",
            )
            .expect("fixed metric is valid"),
        );
    }
    metrics.push(
        crate::system::qualification::QualificationMetric::new(
            "gaming.stutters",
            readiness.stutter_count as f64,
            "count",
            "lower",
            "system",
        )
        .expect("fixed metric is valid"),
    );
    metrics
}

pub fn collect() -> HubSnapshot {
    let doctor = crate::doctor::collect_report();
    let update = crate::system::update_status::read_update_snapshot(600);
    let guardian = crate::guardian::load_state();
    let network = crate::system::probe::read_section("network-summary");
    let ntfs_drives = crate::system::probe::read_section("ntfs-drives")
        .and_then(|value| value.as_array().map(Vec::len))
        .unwrap_or(0);
    let flatpak_apps = crate::system::probe::read_section("flatpak-apps")
        .and_then(|value| value.as_array().map(Vec::len))
        .unwrap_or(0);
    let flatpak_updates = crate::system::probe::read_section("flatpak-updates")
        .and_then(|value| value.as_i64())
        .unwrap_or(0);
    let launchers = crate::system::gaming_library::gaming_library_scan();
    let sessions = crate::system::telemetry::recent_sessions(100);
    HubSnapshot {
        doctor_score: doctor.score,
        doctor_suggestions: doctor.suggestions.len(),
        update_state: update
            .as_ref()
            .map(|snapshot| snapshot.system_state().to_string())
            .unwrap_or_else(|| "unknown".to_string()),
        update_staged: update
            .as_ref()
            .is_some_and(|snapshot| !snapshot.staged_digest.is_empty()),
        guardian_pending: crate::guardian::pending_recommendations(&guardian).len(),
        move_in: move_in_readiness_from(network.as_ref(), ntfs_drives),
        software: SoftwareReadiness {
            installed_flatpaks: flatpak_apps,
            available_flatpak_updates: flatpak_updates,
            appimages: crate::system::software_catalog::appimages().len(),
            starter_packs: crate::system::software_catalog::starter_packs().len(),
        },
        gaming: gaming_readiness_from(&launchers, &sessions),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn aggregates_read_only_fixture_shapes() {
        let network =
            serde_json::json!({"cloud_providers":["drive"], "smb_mounts":2, "vpn_connected":true});
        let move_in = move_in_readiness_from(Some(&network), 3);
        assert_eq!(
            (
                move_in.ntfs_drives,
                move_in.cloud_providers,
                move_in.smb_shares,
                move_in.vpn_connected
            ),
            (3, 1, 2, true)
        );
        let gaming = gaming_readiness_from(
            &[],
            &[
                crate::system::telemetry::SessionRow {
                    game_name: "A".into(),
                    started_at: None,
                    duration_s: Some(60.0),
                    avg_fps: Some(80.0),
                    p1_low_fps: Some(50.0),
                    stutter_count: 2,
                    scheduler: String::new(),
                    avg_latency_ms: None,
                    p99_latency_ms: None,
                },
                crate::system::telemetry::SessionRow {
                    game_name: "B".into(),
                    started_at: None,
                    duration_s: Some(30.0),
                    avg_fps: Some(100.0),
                    p1_low_fps: Some(70.0),
                    stutter_count: 1,
                    scheduler: String::new(),
                    avg_latency_ms: None,
                    p99_latency_ms: None,
                },
            ],
        );
        assert_eq!(gaming.median_fps, Some(90.0));
        assert_eq!(gaming_qualification_metrics(&gaming).len(), 3);

        let snapshot = HubSnapshot {
            doctor_score: 100,
            doctor_suggestions: 0,
            update_state: "current".into(),
            update_staged: false,
            guardian_pending: 0,
            move_in,
            software: SoftwareReadiness {
                installed_flatpaks: 0,
                available_flatpak_updates: 0,
                appimages: 0,
                starter_packs: 0,
            },
            gaming,
        };
        let mut smoke = crate::system::smoke_check::Report::default();
        smoke.passed("Smoke", "ready", "System");
        let report =
            snapshot.qualification_report("2026-08-30T00:00:00Z", Default::default(), &smoke);
        assert_eq!(report.checks.len(), 1);
        assert_eq!(report.metrics.len(), 3);
    }
}
