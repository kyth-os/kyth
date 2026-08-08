"""Cloud rclone pure helpers (Phase H continued)."""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services import cloud_sync  # noqa: E402
from kyth_welcome.services import plasma  # noqa: E402


class RcloneHelperTests(unittest.TestCase):
    def test_config_create_command_onedrive(self):
        cmd = cloud_sync.rclone_config_create_command(
            "od", "onedrive", "tok", extra_params=["drive_type", "personal"],
        )
        self.assertEqual(cmd[:4], ["rclone", "config", "create", "od"])
        self.assertIn("token", cmd)
        self.assertIn("tok", cmd)
        self.assertIn("drive_type", cmd)
        self.assertIn("--non-interactive", cmd)

    def test_create_remote_ok(self):
        with mock.patch(
            "kyth_welcome.services.process.run_command",
            return_value=mock.Mock(returncode=0, stdout="", stderr=""),
        ):
            ok, err = cloud_sync.rclone_create_remote("n", "drive", "{}")
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_create_remote_missing(self):
        with mock.patch(
            "kyth_welcome.services.process.run_command",
            return_value=None,
        ):
            ok, err = cloud_sync.rclone_create_remote("n", "drive", "{}")
        self.assertFalse(ok)
        self.assertIn("not installed", err.lower())

    def test_verify_remote(self):
        with mock.patch(
            "kyth_welcome.services.process.run_command",
            return_value=mock.Mock(returncode=0, stdout="dir", stderr=""),
        ):
            ok, err = cloud_sync.rclone_verify_remote("n")
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_usage_hints(self):
        text = cloud_sync.rclone_usage_hints("gd", "/home/u/Drive")
        self.assertIn("rclone sync gd:", text)
        self.assertIn("rclone mount gd:", text)


class PlasmaShortcutsTests(unittest.TestCase):
    def test_kwriteconfig_command_delete(self):
        cmd = plasma.kwriteconfig_command(
            "kglobalshortcutsrc", ("klipper",), "show-on-mouse-pos", delete=True,
        )
        self.assertIn("--delete", cmd)
        self.assertIn("klipper", cmd)

    def test_apply_windows_shortcuts_no_kwrite(self):
        with mock.patch("shutil.which", return_value=None):
            ok, err = plasma.apply_windows_shortcuts()
        self.assertFalse(ok)
        self.assertIn("kwriteconfig6", err)


class FlatpakPendingCountTests(unittest.TestCase):
    def test_pending_uses_probe_key(self):
        from kyth_welcome.services import flatpak

        with mock.patch.object(
            flatpak, "probe_cached", return_value=4,
        ) as cached:
            n = flatpak.pending_update_count()
        self.assertEqual(n, 4)
        self.assertEqual(cached.call_args[0][0], "flatpak-updates")


if __name__ == "__main__":
    unittest.main()
