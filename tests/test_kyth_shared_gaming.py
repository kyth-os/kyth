"""Unit tests for the shared gaming module."""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared import gaming


class GamingTests(unittest.TestCase):
    @mock.patch("pathlib.Path.exists")
    def test_gamescope_session_active(self, mock_exists):
        mock_exists.return_value = True
        self.assertTrue(gaming.gamescope_session_active(1000))
        mock_exists.assert_called_once_with()

        mock_exists.return_value = False
        self.assertFalse(gaming.gamescope_session_active(1000))

    @mock.patch("subprocess.run")
    def test_gamemode_active(self, mock_run):
        mock_run.return_value = mock.Mock(returncode=0, stdout="1")
        self.assertTrue(gaming.gamemode_active(1000))

        mock_run.return_value = mock.Mock(returncode=0, stdout="0")
        self.assertFalse(gaming.gamemode_active(1000))

        mock_run.return_value = mock.Mock(returncode=1)
        self.assertFalse(gaming.gamemode_active(1000))

    @mock.patch("os.scandir")
    @mock.patch("os.readlink")
    def test_proc_gaming_active(self, mock_readlink, mock_scandir):
        mock_entry = mock.Mock()
        mock_entry.name = "1234"
        mock_scandir.return_value = [mock_entry]

        mock_readlink.return_value = "/usr/bin/gamescope"
        self.assertTrue(gaming.proc_gaming_active())

        mock_readlink.return_value = "/usr/bin/bash"
        self.assertFalse(gaming.proc_gaming_active())

    @mock.patch("kyth_shared.gaming.gamescope_session_active")
    @mock.patch("kyth_shared.gaming.gamemode_active")
    @mock.patch("kyth_shared.gaming.proc_gaming_active")
    @mock.patch("kyth_shared.gaming._active_uids")
    def test_check_gaming_reason(self, mock_uids, mock_proc, mock_gamemode, mock_gamescope):
        mock_uids.return_value = [1000]
        mock_gamescope.return_value = True
        gaming.invalidate_gaming_cache()
        self.assertEqual(gaming.check_gaming_reason(uid=1000), "gamescope session active (uid 1000)")

        mock_gamescope.return_value = False
        mock_gamemode.return_value = True
        gaming.invalidate_gaming_cache()
        self.assertEqual(gaming.check_gaming_reason(uid=1000), "GameMode active (uid 1000)")

        mock_gamemode.return_value = False
        mock_proc.return_value = True
        gaming.invalidate_gaming_cache()
        self.assertEqual(gaming.check_gaming_reason(uid=1000), "gaming process detected (/proc scan)")

        mock_proc.return_value = False
        gaming.invalidate_gaming_cache()
        self.assertIsNone(gaming.check_gaming_reason(uid=1000))


if __name__ == "__main__":
    unittest.main()
