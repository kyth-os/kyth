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

    def test_probe_default_layout_accepts_v4_marker(self):
        def _kread(file_name, group, key):
            if key == "KythComfortLayout":
                return "kyth-comfort-v4"
            return ""

        with mock.patch.object(plasma, "kread", side_effect=_kread):
            probe = plasma._probe_default_layout()
        self.assertEqual(probe.status, "ok")
        self.assertIn("kyth-comfort-v4", probe.details)

    def test_probe_default_layout_accepts_legacy_versions(self):
        for marker in ("kyth-comfort-v2", "kyth-comfort-v3"):
            with self.subTest(marker=marker):
                def _kread(file_name, group, key, _marker=marker):
                    if key == "KythComfortLayout":
                        return _marker
                    return ""

                with mock.patch.object(plasma, "kread", side_effect=_kread):
                    probe = plasma._probe_default_layout()
                self.assertEqual(probe.status, "ok")

    def test_probe_default_layout_dim_when_unset(self):
        with mock.patch.object(plasma, "kread", return_value=""):
            probe = plasma._probe_default_layout()
        self.assertEqual(probe.status, "dim")

    def test_portal_units_summary_prefers_plasma_kde_unit(self):
        def _active(unit: str) -> bool:
            return unit in {
                "xdg-desktop-portal.service",
                "plasma-xdg-desktop-portal-kde.service",
                "pipewire.service",
            }

        with mock.patch.object(plasma, "user_unit_active", side_effect=_active):
            summary = plasma.portal_units_summary()
        self.assertIn("portal:active", summary)
        self.assertIn("plasma-xdg-desktop-portal-kde.service", summary)

    def test_screen_share_summary_ready_with_plasma_portal_unit(self):
        def _active(unit: str) -> bool:
            return unit in {"pipewire.service", "wireplumber.service"}

        with mock.patch.object(plasma, "user_unit_active", side_effect=_active), mock.patch.object(
            plasma,
            "first_active_user_unit",
            return_value="plasma-xdg-desktop-portal-kde.service",
        ):
            summary = plasma.screen_share_summary()
        self.assertTrue(summary.startswith("Ready"))
        self.assertIn("plasma-xdg-desktop-portal-kde.service", summary)

    def test_screen_share_summary_not_ready_without_portal(self):
        with mock.patch.object(plasma, "user_unit_active", return_value=True), mock.patch.object(
            plasma, "first_active_user_unit", return_value=""
        ):
            summary = plasma.screen_share_summary()
        self.assertTrue(summary.startswith("Not ready"))

    def test_nvidia_wayland_summary_without_nvidia(self):
        self.assertEqual(
            plasma.nvidia_wayland_summary("VGA compatible controller: AMD"),
            "No NVIDIA GPU in lspci probe",
        )

    def test_nvidia_wayland_summary_with_smi(self):
        with mock.patch(
            "kyth_shared.system.gpu.query_nvidia_smi",
            return_value="GeForce RTX 4070, 560.35.03",
        ):
            summary = plasma.nvidia_wayland_summary("3D controller: NVIDIA")
        self.assertIn("NVIDIA present", summary)
        self.assertIn("GeForce RTX 4070", summary)

    def test_fractional_scale_summary(self):
        self.assertIn(
            "Fractional scale",
            plasma.fractional_scale_summary("Output: eDP-1\n  Scale: 1.5\n"),
        )
        self.assertIn(
            "Integer scale",
            plasma.fractional_scale_summary("Output: HDMI-1\n  Scale: 1\n"),
        )
        self.assertIn("kscreen-doctor", plasma.fractional_scale_summary(""))


if __name__ == "__main__":
    unittest.main()
