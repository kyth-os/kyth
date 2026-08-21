"""Desktop mode / Plasma Wayland card scripts (source-level, no Qt)."""
from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE_DIR = ROOT / "build_files" / "kyth-welcome" / "kyth_welcome" / "page_plasma_wayland"
PROFILES_SRC = (PAGE_DIR / "_profiles.py").read_text(encoding="utf-8")
CARDS_SRC = (PAGE_DIR / "_cards.py").read_text(encoding="utf-8")


class PlasmaProfilesTests(unittest.TestCase):
    def test_windows_profile_writes_familiar_shortcuts(self):
        self.assertIn('"windows":', PROFILES_SRC)
        self.assertIn("SingleClick false", PROFILES_SRC)
        self.assertIn("Meta+E", PROFILES_SRC)
        self.assertIn("Meta+D", PROFILES_SRC)
        self.assertIn("Meta+L", PROFILES_SRC)
        self.assertIn("result_attr", PROFILES_SRC)

    def test_known_desktop_modes_are_defined(self):
        for key in ("gaming", "dev", "creator", "laptop", "ultrawide", "balanced", "windows"):
            self.assertRegex(PROFILES_SRC, rf'"{key}":\s*\{{')

    def test_profile_apply_reports_err_not_error(self):
        # TaskStatusBadge canonical failure state is "err"
        self.assertIn('set_result("err"', PROFILES_SRC)
        self.assertNotRegex(PROFILES_SRC, r'set_result\("error"')


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
        self.assertIn("_screen_share_status", CARDS_SRC)
        self.assertNotIn('failed = {"Status":', CARDS_SRC)


if __name__ == "__main__":
    unittest.main()
