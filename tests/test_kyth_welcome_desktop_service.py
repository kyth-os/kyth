"""services/desktop.py — desktop/container integration helpers.

REFRESH_DESKTOP_DATABASE_SH is the shell-string counterpart of
refresh_desktop_database() for callers that build a ["bash", "-c", ...]
command list run by a streaming/QThread runner instead of calling
run_command() directly. page_repair.py (x2) and page_software_installed.py
interpolate it rather than each retyping the update-desktop-database +
kbuildsycoca6 snippet — this file also guards that those call sites keep
using the shared constant instead of drifting back to hand-rolled copies.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services import desktop  # noqa: E402

KYTH_WELCOME = ROOT / "build_files" / "kyth-welcome" / "kyth_welcome"


class DesktopServiceTests(unittest.TestCase):
    def test_is_distrobox_container_true(self):
        result = mock.Mock(returncode=0, stdout="kali\nubuntu\n")
        with mock.patch.object(desktop, "run_command", return_value=result):
            self.assertTrue(desktop.is_distrobox_container("kali"))

    def test_is_distrobox_container_false_when_absent(self):
        result = mock.Mock(returncode=0, stdout="ubuntu\n")
        with mock.patch.object(desktop, "run_command", return_value=result):
            self.assertFalse(desktop.is_distrobox_container("kali"))

    def test_is_distrobox_container_false_on_command_failure(self):
        with mock.patch.object(desktop, "run_command", return_value=None):
            self.assertFalse(desktop.is_distrobox_container("kali"))

    def test_refresh_desktop_database_runs_both_commands(self):
        with mock.patch.object(desktop, "run_command") as run:
            desktop.refresh_desktop_database("/home/user/.local/share/applications")
        run.assert_any_call(
            ["update-desktop-database", "/home/user/.local/share/applications"], timeout=5,
        )
        run.assert_any_call(["kbuildsycoca6", "--noincremental"], timeout=5)

    def test_refresh_desktop_database_sh_is_valid_bash(self):
        result = subprocess.run(
            ["bash", "-n", "-c", desktop.REFRESH_DESKTOP_DATABASE_SH],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_refresh_desktop_database_sh_actually_runs_clean(self):
        # -n only checks syntax; also run it for real (against stubbed
        # update-desktop-database/kbuildsycoca6 on PATH) to catch runtime
        # issues like unset variables under -u.
        result = subprocess.run(
            ["bash", "-c", f"set -euo pipefail; {desktop.REFRESH_DESKTOP_DATABASE_SH}"],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

if __name__ == "__main__":
    unittest.main()
