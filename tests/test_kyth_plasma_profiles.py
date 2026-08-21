"""Desktop mode / Plasma Wayland card scripts (source-level, no Qt)."""
from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE_DIR = ROOT / "build_files" / "kyth-welcome" / "kyth_welcome" / "page_plasma_wayland"
PROFILES_SRC = (PAGE_DIR / "_profiles.py").read_text(encoding="utf-8")
CARDS_SRC = (PAGE_DIR / "_cards.py").read_text(encoding="utf-8")
REPAIR_SRC = (PAGE_DIR / "_repair.py").read_text(encoding="utf-8")
POLISH_SRC = (PAGE_DIR / "_polish.py").read_text(encoding="utf-8")
INIT_SRC = (PAGE_DIR / "__init__.py").read_text(encoding="utf-8")


class PlasmaProfilesTests(unittest.TestCase):
    def test_windows_profile_writes_familiar_shortcuts(self):
        self.assertIn('"windows":', PROFILES_SRC)
        self.assertIn("SingleClick false", PROFILES_SRC)
        self.assertIn("Meta+E", PROFILES_SRC)
        self.assertIn("Meta+D", PROFILES_SRC)
        self.assertIn("Meta+L", PROFILES_SRC)
        self.assertIn("Meta+V", PROFILES_SRC)
        self.assertIn("result_attr", PROFILES_SRC)
        # Plasma 6 nested services group — not a flat services key
        self.assertIn("--group services --group org.kde.dolphin.desktop --key _launch", PROFILES_SRC)
        self.assertNotIn("--group services --key 'org.kde.dolphin.desktop'", PROFILES_SRC)
        # Bogus Containments alignment write removed
        self.assertNotIn("Containments --key alignment", PROFILES_SRC)

    def test_known_desktop_modes_are_defined(self):
        for key in ("gaming", "dev", "creator", "laptop", "ultrawide", "balanced", "windows"):
            self.assertRegex(PROFILES_SRC, rf'"{key}":\s*\{{')

    def test_profile_apply_reports_err_not_error(self):
        # TaskStatusBadge canonical failure state is "err"
        self.assertIn('set_result("err"', PROFILES_SRC)
        self.assertNotRegex(PROFILES_SRC, r'set_result\("error"')

    def test_profile_apply_uses_background_worker(self):
        self.assertIn("DataWorker(", PROFILES_SRC)
        self.assertIn("_on_desktop_profile_done", PROFILES_SRC)


class PlasmaCardsSourceTests(unittest.TestCase):
    def test_windows_parity_lays_out_clipboard_row(self):
        # Regression: clip ActionRow was built then discarded; Clipboard/FancyZones never shown.
        self.assertIn("body.addWidget(clip)", CARDS_SRC)
        self.assertIn("clip.finish()", CARDS_SRC)

    def test_action_rows_call_finish(self):
        self.assertGreaterEqual(CARDS_SRC.count(".finish()"), 5)

    def test_wayland_readiness_maps_failures_to_known_rows(self):
        self.assertIn("_WAYLAND_ROW_NAMES", CARDS_SRC)
        self.assertIn("_on_wayland_readiness_failed", CARDS_SRC)
        self.assertIn("screen_share_summary", CARDS_SRC)
        self.assertIn("portal_units_summary", CARDS_SRC)
        self.assertIn("nvidia_wayland_summary", CARDS_SRC)
        self.assertIn("fractional_scale_summary", CARDS_SRC)
        self.assertNotIn('failed = {"Status":', CARDS_SRC)

    def test_dead_presets_card_removed(self):
        self.assertNotIn("_make_presets_card", CARDS_SRC)
        self.assertNotIn("_make_presets_card", INIT_SRC)

    def test_kcm_failures_route_locally(self):
        self.assertIn("status_badge=actions.status", CARDS_SRC)
        self.assertIn('result_attr="_polish_result"', CARDS_SRC)

    def test_fancyzones_uses_background_worker(self):
        self.assertIn("DataWorker(", CARDS_SRC)
        self.assertIn("_on_fancyzones_done", CARDS_SRC)


class PlasmaRepairPolishSourceTests(unittest.TestCase):
    def test_repair_and_polish_use_background_workers(self):
        self.assertIn("DataWorker(", REPAIR_SRC)
        self.assertIn("_on_repair_command_done", REPAIR_SRC)
        self.assertIn("DataWorker(", POLISH_SRC)
        self.assertIn("_on_plasma_polish_done", POLISH_SRC)

    def test_open_kcm_accepts_local_feedback_targets(self):
        self.assertIn("status_badge", REPAIR_SRC)
        self.assertIn("result_attr", REPAIR_SRC)


if __name__ == "__main__":
    unittest.main()
