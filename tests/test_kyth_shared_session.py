"""Unit tests for the shared session module."""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.session import (
    check_firstboot_app_status,
    disable_vscode_brave_wallet_prompts,
    write_chromium_flags,
    write_code_argv,
)


class SessionTests(unittest.TestCase):
    @mock.patch("pathlib.Path.is_file")
    @mock.patch("pathlib.Path.read_text")
    @mock.patch("pathlib.Path.write_text")
    def test_write_code_argv(self, mock_write, mock_read, mock_is_file) -> None:
        mock_is_file.return_value = True
        mock_read.return_value = '{"some-setting": true}'
        p = pathlib.Path("/dummy/argv.json")
        write_code_argv(p)
        mock_write.assert_called_once()
        self.assertIn('"password-store": "basic"', mock_write.call_args[0][0])

    @mock.patch("pathlib.Path.is_file")
    @mock.patch("pathlib.Path.read_text")
    @mock.patch("pathlib.Path.write_text")
    def test_write_chromium_flags(self, mock_write, mock_read, mock_is_file) -> None:
        mock_is_file.return_value = True
        mock_read.return_value = "--enable-features=UseOzonePlatform\n"
        p = pathlib.Path("/dummy/flags.conf")
        write_chromium_flags(p)
        mock_write.assert_called_once()
        self.assertIn("--password-store=basic", mock_write.call_args[0][0])

    @mock.patch("kyth_shared.session.write_chromium_flags")
    @mock.patch("kyth_shared.session.write_code_argv")
    def test_disable_vscode_brave_wallet_prompts(self, mock_argv, mock_flags) -> None:
        disable_vscode_brave_wallet_prompts(pathlib.Path("/dummy/home"))
        mock_argv.assert_called_once()
        self.assertEqual(mock_flags.call_count, 7)

    @mock.patch("shutil.which")
    @mock.patch("subprocess.run")
    @mock.patch("pathlib.Path.is_file")
    @mock.patch("time.sleep")
    def test_check_firstboot_app_status_ready(self, mock_sleep, mock_is_file, mock_run, mock_which) -> None:
        mock_which.return_value = "/bin/flatpak"
        mock_is_file.return_value = False

        # Mock flatpak info App ID commands: returncode=0 means installed
        mock_run.return_value = mock.Mock(returncode=0)

        with mock.patch("kyth_shared.session.write_app_status") as mock_write_status:
            ret = check_firstboot_app_status(force=True, delay=0)
            self.assertEqual(ret, 0)
            mock_write_status.assert_called_once_with(
                mock.ANY,
                "ready",
                "Steam, launchers, Bottles, and save backup tools are installed.",
            )


if __name__ == "__main__":
    unittest.main()
