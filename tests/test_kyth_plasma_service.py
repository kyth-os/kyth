"""Plasma / Wayland pure service helpers (no Qt)."""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services import plasma  # noqa: E402


class PlasmaServiceTests(unittest.TestCase):
    def test_session_kind_from_env(self):
        with mock.patch.dict("os.environ", {"XDG_SESSION_TYPE": "wayland"}, clear=False):
            self.assertEqual(plasma.session_kind(), "wayland")

    def test_desktop_name_prefers_current_desktop(self):
        with mock.patch.dict(
            "os.environ",
            {"XDG_CURRENT_DESKTOP": "KDE", "DESKTOP_SESSION": "plasma"},
            clear=False,
        ):
            self.assertEqual(plasma.desktop_name(), "KDE")

    def test_collect_wayland_probes_shape(self):
        with mock.patch.object(plasma, "run_text", return_value=(1, "", "")), mock.patch(
            "shutil.which", return_value=None
        ), mock.patch.dict(
            "os.environ",
            {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "KDE"},
            clear=False,
        ):
            probes = plasma.collect_wayland_probes()
        self.assertGreaterEqual(len(probes), 5)
        titles = {p.title for p in probes}
        self.assertIn("Session", titles)
        self.assertIn("Plasma desktop", titles)


if __name__ == "__main__":
    unittest.main()
