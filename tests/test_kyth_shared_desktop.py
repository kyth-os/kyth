"""Unit tests for the shared desktop configuration module."""
from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.desktop import plasma


class DesktopPlasmaTests(unittest.TestCase):
    @mock.patch("pathlib.Path.is_file")
    def test_desktop_exists(self, mock_is_file):
        mock_is_file.side_effect = lambda: True
        self.assertTrue(plasma.desktop_exists("test.desktop"))
        self.assertTrue(plasma.desktop_exists("applications:test.desktop"))

        mock_is_file.side_effect = lambda: False
        self.assertFalse(plasma.desktop_exists("test.desktop"))

    @mock.patch("kyth_shared.desktop.plasma.desktop_exists")
    def test_filter_available_launchers(self, mock_exists):
        mock_exists.side_effect = lambda d: d == "com.valvesoftware.Steam.desktop"
        config = [
            "applications:kyth-welcome.desktop",
            ["applications:com.valvesoftware.Steam.desktop", "applications:steam.desktop"],
        ]
        res = plasma.filter_available_launchers(config)
        self.assertEqual(res, ["applications:com.valvesoftware.Steam.desktop"])

    @mock.patch("shutil.which")
    def test_get_qdbus_command(self, mock_which):
        mock_which.side_effect = lambda c: f"/usr/bin/{c}" if c == "qdbus-qt6" else None
        self.assertEqual(plasma.get_qdbus_command(), "/usr/bin/qdbus-qt6")

    @mock.patch("subprocess.run")
    @mock.patch("kyth_shared.desktop.plasma.get_qdbus_command")
    def test_evaluate_plasma_script(self, mock_get_qdbus, mock_run):
        mock_get_qdbus.return_value = "/usr/bin/qdbus6"
        mock_run.return_value = mock.Mock(returncode=0)
        self.assertTrue(plasma.evaluate_plasma_script("print('hello')"))
        mock_run.assert_called_once_with(
            ["/usr/bin/qdbus6", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript", "print('hello')"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    @mock.patch("subprocess.run")
    @mock.patch("shutil.which")
    def test_kreadconfig(self, mock_which, mock_run):
        mock_which.return_value = "/usr/bin/kreadconfig6"
        mock_run.return_value = mock.Mock(returncode=0, stdout="val\n")
        self.assertEqual(plasma.kreadconfig("file", "group", "key"), "val")

    @mock.patch("subprocess.run")
    @mock.patch("shutil.which")
    def test_kwriteconfig(self, mock_which, mock_run):
        mock_which.return_value = "/usr/bin/kwriteconfig6"
        mock_run.return_value = mock.Mock(returncode=0)
        self.assertTrue(plasma.kwriteconfig("file", "group", "key", "value", "bool"))
        mock_run.assert_called_once_with(
            ["/usr/bin/kwriteconfig6", "--file", "file", "--group", "group", "--key", "key", "--type", "bool", "value"],
            capture_output=True,
            timeout=5,
            check=False,
        )

    @mock.patch("kyth_shared.desktop.plasma.evaluate_plasma_script")
    @mock.patch("kyth_shared.desktop.plasma.kwriteconfig")
    @mock.patch("kyth_shared.desktop.plasma.filter_available_launchers")
    @mock.patch("kyth_shared.desktop.plasma.get_qdbus_command")
    @mock.patch("kyth_shared.desktop.plasma.kreadconfig")
    def test_apply_desktop_layout_skip(self, mock_read, mock_qdbus, mock_filter, mock_write, mock_eval):
        mock_read.side_effect = lambda f, g, k: plasma.LAYOUT_VERSION if k == "KythComfortLayout" else None
        self.assertEqual(plasma.apply_desktop_layout(), 0)

    @mock.patch("kyth_shared.desktop.plasma.evaluate_plasma_script")
    @mock.patch("kyth_shared.desktop.plasma.kwriteconfig")
    @mock.patch("kyth_shared.desktop.plasma.filter_available_launchers")
    @mock.patch("kyth_shared.desktop.plasma.get_qdbus_command")
    @mock.patch("kyth_shared.desktop.plasma.kreadconfig")
    def test_apply_desktop_layout_refuse(self, mock_read, mock_qdbus, mock_filter, mock_write, mock_eval):
        mock_read.return_value = None
        self.assertEqual(plasma.apply_desktop_layout(), 64)

    @mock.patch("kyth_shared.desktop.plasma.evaluate_plasma_script")
    @mock.patch("kyth_shared.desktop.plasma.kwriteconfig")
    @mock.patch("kyth_shared.desktop.plasma.filter_available_launchers")
    @mock.patch("kyth_shared.desktop.plasma.get_qdbus_command")
    @mock.patch("kyth_shared.desktop.plasma.kreadconfig")
    def test_apply_desktop_layout_apply(self, mock_read, mock_qdbus, mock_filter, mock_write, mock_eval):
        mock_read.return_value = None
        mock_qdbus.return_value = "/usr/bin/qdbus"
        mock_filter.return_value = ["applications:steam.desktop"]
        mock_eval.return_value = True
        mock_write.return_value = True

        self.assertEqual(plasma.apply_desktop_layout(initial=True), 0)
        mock_eval.assert_called_once()
        mock_write.assert_called_once_with(plasma.CONFIG_FILE, "KythOS", "KythComfortLayout", plasma.LAYOUT_VERSION)

    @mock.patch("pathlib.Path.write_text")
    @mock.patch("pathlib.Path.mkdir")
    @mock.patch("kyth_shared.desktop.plasma.evaluate_plasma_script")
    @mock.patch("kyth_shared.desktop.plasma.filter_available_launchers")
    @mock.patch("kyth_shared.desktop.plasma.get_qdbus_command")
    @mock.patch("kyth_shared.desktop.plasma.kreadconfig")
    def test_refresh_taskbar_pins(self, mock_read, mock_qdbus, mock_filter, mock_eval, mock_mkdir, mock_write):
        mock_read.return_value = "kyth-comfort-v4"
        mock_qdbus.return_value = "/usr/bin/qdbus"
        mock_filter.return_value = ["applications:steam.desktop"]
        mock_eval.return_value = True

        self.assertEqual(plasma.refresh_taskbar_pins(), 0)
        mock_eval.assert_called_once()
        mock_write.assert_called_once()


if __name__ == "__main__":
    unittest.main()
