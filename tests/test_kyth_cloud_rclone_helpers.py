"""Cloud rclone pure helpers (Phase H continued)."""
from __future__ import annotations

import pathlib
import configparser
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services import cloud_sync  # noqa: E402
from kyth_welcome.services import plasma  # noqa: E402


class RcloneHelperTests(unittest.TestCase):
    def test_create_remote_writes_private_config_without_subprocess_token(self):
        token = '{"access_token":"very-secret","refresh_token":"refresh"}'
        with tempfile.TemporaryDirectory() as tmpdir, \
             mock.patch.dict(os.environ, {"RCLONE_CONFIG": f"{tmpdir}/rclone.conf"}, clear=False), \
             mock.patch("shutil.which", return_value="/usr/bin/rclone"), \
             mock.patch("subprocess.run") as run:
            ok, err = cloud_sync.rclone_create_remote(
                "od", "onedrive", token,
                extra_params=["drive_type", "personal"],
            )
            config_path = pathlib.Path(tmpdir) / "rclone.conf"
            parser = configparser.RawConfigParser(interpolation=None)
            parser.read(config_path, encoding="utf-8")

            self.assertTrue(ok, err)
            self.assertEqual(parser["od"]["type"], "onedrive")
            self.assertEqual(json.loads(parser["od"]["token"])["access_token"], "very-secret")
            self.assertEqual(parser["od"]["drive_type"], "personal")
            self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)
            run.assert_not_called()

    def test_create_remote_missing(self):
        with mock.patch("shutil.which", return_value=None):
            ok, err = cloud_sync.rclone_create_remote("n", "drive", '{"access_token":"token"}')
        self.assertFalse(ok)
        self.assertIn("not installed", err.lower())

    def test_create_remote_rejects_invalid_token_and_symlink_config(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
             mock.patch.dict(os.environ, {"RCLONE_CONFIG": f"{tmpdir}/rclone.conf"}, clear=False), \
             mock.patch("shutil.which", return_value="/usr/bin/rclone"):
            ok, err = cloud_sync.rclone_create_remote("remote", "drive", "{}")
            self.assertFalse(ok)
            self.assertIn("access_token", err)

            target = pathlib.Path(tmpdir) / "target"
            target.write_text("unchanged", encoding="utf-8")
            (pathlib.Path(tmpdir) / "rclone.conf").symlink_to(target)
            ok, err = cloud_sync.rclone_create_remote(
                "remote", "drive", '{"access_token":"secret"}',
            )
            self.assertFalse(ok)
            self.assertIn("regular user-owned", err)
            self.assertEqual(target.read_text(encoding="utf-8"), "unchanged")

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
