"""Regression coverage for Hub launch and navigation responsiveness."""

from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
HUB = ROOT / "src" / "kyth-hub-web"
WEB_SRC = HUB / "src"
LIVE_DATA = (WEB_SRC / "services" / "liveData.ts").read_text(encoding="utf-8")
HUB_PAGE = (WEB_SRC / "pages" / "HubPage.tsx").read_text(encoding="utf-8")
PLAY_PAGE = (WEB_SRC / "pages" / "Play.tsx").read_text(encoding="utf-8")
PERFORMANCE_CHART = (WEB_SRC / "components" / "PerformanceChart.tsx").read_text(encoding="utf-8")
SESSIONS_CHART = (WEB_SRC / "components" / "SessionsChart.tsx").read_text(encoding="utf-8")
VITE_CONFIG = (HUB / "vite.config.ts").read_text(encoding="utf-8")
MAIN_RS = (HUB / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")
DASHBOARD_RS = (HUB / "src-tauri" / "src" / "commands" / "dashboard.rs").read_text(encoding="utf-8")


class HubWebPerformanceTests(unittest.TestCase):
    def test_overview_destinations_do_not_mount_a_workspace_by_default(self) -> None:
        self.assertIn("defaultToFirstSection = false", HUB_PAGE)
        self.assertIn("const active = sections.find", HUB_PAGE)
        self.assertIn("defaultToFirstSection ? sections[0] : null", HUB_PAGE)

        for page in ("Apps.tsx", "MoveIn.tsx", "Play.tsx", "ThisPc.tsx"):
            source = (WEB_SRC / "pages" / page).read_text(encoding="utf-8")
            self.assertNotIn("defaultToFirstSection", source, page)
        for page in ("Updates.tsx", "Vpn.tsx"):
            source = (WEB_SRC / "pages" / page).read_text(encoding="utf-8")
            self.assertIn("defaultToFirstSection", source, page)

    def test_expensive_bridge_reads_are_shared_and_short_lived(self) -> None:
        self.assertIn("const sharedReads = new Map", LIVE_DATA)
        self.assertIn("async function sharedRead", LIVE_DATA)
        for key in (
            '"installed-flatpaks"',
            '"pending-updates"',
            '"update-status"',
            '"update-health"',
            '"bootc-snapshot"',
        ):
            self.assertIn(key, LIVE_DATA)
        self.assertIn("invalidateSharedReads", LIVE_DATA)

    def test_play_defers_charts_and_reuses_overview_telemetry(self) -> None:
        self.assertIn('lazy(() => import("../components/PerformanceChart")', PLAY_PAGE)
        self.assertIn('lazy(() => import("../components/SessionsChart")', PLAY_PAGE)
        self.assertIn("Show performance charts", PLAY_PAGE)
        self.assertIn("onTelemetryLoaded", PLAY_PAGE)
        self.assertNotIn("fetchTelemetryRecent", PERFORMANCE_CHART)
        self.assertNotIn("fetchTelemetryRecent", SESSIONS_CHART)

    def test_subprocess_backed_reads_use_the_blocking_runtime(self) -> None:
        for command in (
            "async fn network_identity",
            "async fn installed_flatpaks",
            "async fn desktop_stack_checks",
            "async fn controllers_detect",
            "async fn btrfs_health",
            "async fn mok_status",
        ):
            self.assertIn(command, MAIN_RS)
        for command in ("async fn hardware_snapshot", "async fn boot_runtime_checks"):
            self.assertIn(command, DASHBOARD_RS)
        self.assertGreaterEqual(MAIN_RS.count("spawn_blocking"), 6)
        self.assertGreaterEqual(DASHBOARD_RS.count("spawn_blocking"), 3)

    def test_embedded_production_frontend_does_not_ship_source_maps(self) -> None:
        self.assertIn("sourcemap: false", VITE_CONFIG)


if __name__ == "__main__":
    unittest.main()
