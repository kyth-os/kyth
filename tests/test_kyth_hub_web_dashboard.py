"""The React dashboard must not present fixtures as this machine's facts.

Every tile on the dashboard fetched a live value, but `statTiles.map(...)`
returned the *mock* tile whenever a fetch resolved null — so outside the
Tauri shell, or on any failed read, "412 GB" and "RX 7900 XTX" rendered as
though they were the user's own hardware. The gauges asserted provenance
they never had ("From Guardian's last check" over a hardcoded 95), the
performance card claimed a "+18% vs last week" comparison against data it
never fetched, and HeroCard greeted every user as "Mark".

The telemetry charts are the one place fixtures remain, and that is
deliberate: kyth-telem collects real sessions, but its reader has no Rust
port yet (see ChartFixtureNote). Those cards must therefore *say* they are
samples rather than silently imply live data.

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
HERO_CARD = (HUB_WEB / "components" / "HeroCard.tsx").read_text(encoding="utf-8")
GAUGE_CARD = (HUB_WEB / "components" / "GaugeCard.tsx").read_text(encoding="utf-8")
PERF_CHART = (HUB_WEB / "components" / "PerformanceChart.tsx").read_text(encoding="utf-8")
SESSIONS_CHART = (HUB_WEB / "components" / "SessionsChart.tsx").read_text(encoding="utf-8")
LIVE_DATA = (HUB_WEB / "services" / "liveData.ts").read_text(encoding="utf-8")
MAIN_RS = (ROOT / "src" / "kyth-hub-web" / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")

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

    def test_fixture_charts_declare_themselves(self):
        for name, source in (("PerformanceChart", PERF_CHART), ("SessionsChart", SESSIONS_CHART)):
            code = _code_only(source)
            self.assertIn("ChartFixtureNote", code, f"{name} must label its fixture data")
            self.assertIn("Sample data", code, f"{name} must carry the sample badge")

    def test_chart_note_does_not_claim_an_empty_read(self):
        # Rendered copy only — the file's own comment names the phrasing to
        # avoid, so checking the raw source would match that explanation.
        note = _code_only((HUB_WEB / "components" / "ChartFixtureNote.tsx").read_text(encoding="utf-8"))
        # kyth-telem may well have sessions on disk; we simply never look.
        for false_claim in ("No sessions yet", "no sessions recorded", "No sessions recorded"):
            self.assertNotIn(false_claim, note)
        self.assertIn("isn't", note.replace("’", "'"))

    def test_performance_chart_drops_unearned_provenance(self):
        # It claimed capture by kyth-telem while drawing fixture numbers.
        self.assertNotIn("captured by kyth-telem", _code_only(PERF_CHART))


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


if __name__ == "__main__":
    unittest.main()
