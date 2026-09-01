"""The React dashboard must not present fixtures as this machine's facts.

Every tile on the dashboard fetched a live value, but `statTiles.map(...)`
returned the *mock* tile whenever a fetch resolved null — so outside the
Tauri shell, or on any failed read, "412 GB" and "RX 7900 XTX" rendered as
though they were the user's own hardware. The gauges asserted provenance
they never had ("From Guardian's last check" over a hardcoded 95), the
performance card claimed a "+18% vs last week" comparison against data it
never fetched, and HeroCard greeted every user as "Mark".

The telemetry charts read real sessions through the Rust bridge when the
shell is available, and explicitly show a no-data state otherwise. They must
not silently fall back to the old mock series.

TypeScript can't catch any of this — a fixture is a well-typed value — so
these are static checks over the shipped sources.
"""
from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HUB_WEB = ROOT / "src" / "kyth-hub-web" / "src"
DASHBOARD = (HUB_WEB / "pages" / "Dashboard.tsx").read_text(encoding="utf-8")
PLAY = (HUB_WEB / "pages" / "Play.tsx").read_text(encoding="utf-8")
HERO_CARD = (HUB_WEB / "components" / "HeroCard.tsx").read_text(encoding="utf-8")
GAUGE_CARD = (HUB_WEB / "components" / "GaugeCard.tsx").read_text(encoding="utf-8")
PERF_CHART = (HUB_WEB / "components" / "PerformanceChart.tsx").read_text(encoding="utf-8")
SESSIONS_CHART = (HUB_WEB / "components" / "SessionsChart.tsx").read_text(encoding="utf-8")
LIVE_DATA = (HUB_WEB / "services" / "liveData.ts").read_text(encoding="utf-8")
TAURI_SRC = ROOT / "src" / "kyth-hub-web" / "src-tauri" / "src"
MAIN_RS = (TAURI_SRC / "main.rs").read_text(encoding="utf-8")
MAIN_RS += "\n" + "\n".join(path.read_text(encoding="utf-8") for path in sorted((TAURI_SRC / "commands").glob("*.rs")))
GUARDIAN_CARD = (HUB_WEB / "components" / "GuardianHistoryCard.tsx").read_text(encoding="utf-8")
TOPBAR = (HUB_WEB / "components" / "Topbar.tsx").read_text(encoding="utf-8")
RECOVERY_RS = (
    ROOT / "src" / "kyth-shared-rs" / "src" / "system" / "recovery_status.rs"
).read_text(encoding="utf-8")

# Values that only ever existed in mockDashboard.ts. If one of these turns
# up in a rendered tile again, a fixture is being shown as a system fact.
FIXTURE_VALUES = ("412 GB", "RX 7900 XTX", "-8 GB this week")


def _code_only(source: str) -> str:
    """Strip comments so prose about a fixture never satisfies a check."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith(("//", "*"))
    )


DASHBOARD_CODE = _code_only(DASHBOARD)
HERO_CODE = _code_only(HERO_CARD)
GUARDIAN_CODE = _code_only(GUARDIAN_CARD)
TOPBAR_CODE = _code_only(TOPBAR)


class DashboardHonestyTests(unittest.TestCase):
    def test_dashboard_never_renders_fixture_tile_values(self):
        for value in FIXTURE_VALUES:
            self.assertNotIn(
                value,
                DASHBOARD_CODE,
                f"{value!r} is a mockDashboard fixture — a failed read must render a "
                "placeholder, not someone else's hardware",
            )

    def test_dashboard_does_not_import_fixture_tiles_as_values(self):
        # The StatTile/GuardianEvent *types* are fine; importing the
        # statTiles array back is what reintroduces the fallback.
        self.assertNotRegex(
            DASHBOARD_CODE,
            r"import\s*\{[^}]*\bstatTiles\b",
            "Dashboard must build its tiles from live reads, not from the fixture array",
        )

    def test_every_stat_tile_has_a_pending_placeholder(self):
        # Four tiles, each of which must degrade rather than keep a fixture.
        self.assertGreaterEqual(
            DASHBOARD_CODE.count("PENDING"),
            4,
            "each tile needs an explicit no-reading fallback",
        )

    def test_hero_card_is_not_given_a_literal_name(self):
        self.assertNotRegex(
            DASHBOARD_CODE,
            r"<HeroCard[^>]*name=\"[A-Za-z]",
            "HeroCard must receive the live identity read, never a hardcoded person",
        )

    def test_hero_card_has_no_hardcoded_person_anywhere(self):
        self.assertNotIn("Mark", HERO_CODE)

    def test_hero_card_distinguishes_unknown_guardian_state(self):
        # "no answer yet" must not render as "answered: all clear".
        self.assertIn("pendingCount === null", HERO_CODE)
        self.assertNotIn("Guardian found nothing new to fix today", HERO_CODE)

    def test_gauges_are_not_hardcoded_scores(self):
        for literal in (r"value=\{95\}", r"value=\{9\.3\}"):
            self.assertNotRegex(
                DASHBOARD_CODE,
                literal,
                "a gauge must derive from a real read or show no reading",
            )

    def test_gauge_card_renders_a_no_reading_state(self):
        self.assertIn("value === null", _code_only(GAUGE_CARD))

    def test_gauges_derive_from_real_reads(self):
        for fetcher in ("fetchBootRuntimeChecks", "fetchRecoveryStatus"):
            self.assertIn(fetcher, DASHBOARD_CODE)

    def test_no_fabricated_week_over_week_comparison(self):
        # A derived comparison over a series that is never fetched.
        self.assertNotIn("vs last week", _code_only(PERF_CHART))

    def test_charts_use_the_live_telemetry_bridge(self):
        for name, source in (("PerformanceChart", PERF_CHART), ("SessionsChart", SESSIONS_CHART)):
            code = _code_only(source)
            self.assertIn("fetchTelemetryRecent", code, f"{name} must read the telemetry bridge")
            self.assertIn('"Live"', code, f"{name} must identify live data")
            self.assertIn('"Preview"', code, f"{name} must identify the no-data state")

    def test_charts_do_not_import_fixture_series(self):
        for name, source in (("PerformanceChart", PERF_CHART), ("SessionsChart", SESSIONS_CHART)):
            code = _code_only(source)
            self.assertNotIn("mockDashboard", code, f"{name} must not render dashboard fixtures")
            self.assertNotIn("ChartFixtureNote", code, f"{name} must not claim its data is a fixture")

    def test_live_chart_no_data_copy_does_not_claim_a_fixture_read(self):
        for source in (PERF_CHART, SESSIONS_CHART):
            code = _code_only(source)
            self.assertNotIn("Sample figures", code)
            self.assertNotIn("isn't wired", code)

class PagePlacementTests(unittest.TestCase):
    def test_gaming_activity_charts_live_under_play_not_home(self):
        for chart in ("PerformanceChart", "SessionsChart"):
            self.assertNotIn(chart, _code_only(DASHBOARD), f"{chart} must not be a Home card")
            self.assertIn(chart, _code_only(PLAY), f"{chart} belongs in the Play section")
        self.assertIn("Gaming activity", PLAY)
        self.assertNotIn("Performance and Guardian history", DASHBOARD)


class IdentityReadTests(unittest.TestCase):
    def test_identity_command_is_registered_in_the_shell(self):
        self.assertRegex(MAIN_RS, r"fn current_user_name\(\)")
        handler = MAIN_RS.split("generate_handler!")[1]
        self.assertIn("current_user_name", handler.split("]")[0])

    def test_identity_bridge_exists_and_is_used(self):
        self.assertIn("export async function fetchUserName", LIVE_DATA)
        self.assertIn("fetchUserName", DASHBOARD_CODE)

    def test_identity_bridge_returns_null_rather_than_a_placeholder(self):
        body = LIVE_DATA.split("export async function fetchUserName")[1].split("\n}")[0]
        self.assertIn("return null", body)
        self.assertNotRegex(body, r"return \"[A-Za-z]")


class GuardianHistoryHonestyTests(unittest.TestCase):
    """The activity card had the same fallback bug the stat tiles did.

    `events` defaulted to mockDashboard's `guardianHistory`, so a failed
    Guardian read rendered four invented events as this machine's health
    history — distinguished only by a missing badge.
    """

    def test_card_never_falls_back_to_the_history_fixture(self):
        self.assertNotIn("guardianHistory", GUARDIAN_CODE)

    def test_events_prop_is_required(self):
        # An optional prop is what allows the default to come back.
        self.assertNotIn("events?:", GUARDIAN_CODE)
        self.assertIn("events: GuardianEvent[]", GUARDIAN_CODE)

    def test_card_renders_an_empty_state(self):
        self.assertIn("visibleEvents.length === 0", GUARDIAN_CODE)

    def test_dashboard_passes_a_concrete_list(self):
        self.assertRegex(DASHBOARD_CODE, r"guardianEvents: GuardianEvent\[\]")
        self.assertIn("?? []", DASHBOARD_CODE)


class RecoveryDerivationTests(unittest.TestCase):
    """`watcher_staged` is not a safeguard, so it must not count as one."""

    def test_watcher_staged_is_merely_has_staged(self):
        # Guards the premise: if the Rust ever gives watcher_staged its own
        # meaning, this test fails and the dashboard maths gets revisited.
        self.assertIn("watcher_staged: has_staged", _code_only(RECOVERY_RS))

    def test_a_staged_update_is_not_counted_as_a_missing_safeguard(self):
        self.assertNotIn("watcher_staged", DASHBOARD_CODE)

    def test_safeguards_are_only_real_safety_properties(self):
        self.assertIn("recovery.has_rollback", DASHBOARD_CODE)
        self.assertIn("!recovery.quarantined_digest", DASHBOARD_CODE)

    def test_safeguard_total_matches_the_number_counted(self):
        self.assertIn("max={2}", DASHBOARD_CODE)
        self.assertIn("of 2 safeguards ready", DASHBOARD_CODE)
        self.assertNotIn("of 3 safeguards", DASHBOARD_CODE)

    def test_empty_boot_checks_do_not_claim_we_never_looked(self):
        note = DASHBOARD_CODE.split("pendingNote=")[1].split("\n")[0]
        self.assertIn("bootChecks ?", note)


class NotificationLabelTests(unittest.TestCase):
    def test_unknown_guardian_state_is_not_announced_as_healthy(self):
        # null means Guardian has not answered; a screen reader must not be
        # told "nothing needs attention" before there is an answer.
        # Split on the next prop, not "}": the label itself contains a
        # template-literal "}" that would truncate the region under test.
        label = TOPBAR_CODE.split("aria-label={")[-1].split("onClick=")[0]
        self.assertIn("pendingCount === null", label)
        self.assertLess(
            label.index("pendingCount === null"),
            label.index("nothing needs attention"),
        )


if __name__ == "__main__":
    unittest.main()
