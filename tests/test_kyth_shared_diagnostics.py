"""Unit tests for the shared diagnostics module."""
from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.diagnostics import DiagnosticReporter, run_health_checks


class DiagnosticsTests(unittest.TestCase):
    def test_init(self) -> None:
        reporter = DiagnosticReporter("Test Title")
        self.assertEqual(reporter.title, "Test Title")
        self.assertEqual(reporter.warnings, 0)
        self.assertEqual(reporter.failures, 0)

    @mock.patch("shutil.which")
    def test_have(self, mock_which) -> None:
        reporter = DiagnosticReporter("Test")
        mock_which.return_value = "/bin/ls"
        self.assertTrue(reporter.have("ls"))

        mock_which.return_value = None
        self.assertFalse(reporter.have("nonexistent"))

    @mock.patch("sys.exit")
    def test_print_result_success(self, mock_exit) -> None:
        reporter = DiagnosticReporter("Test")
        reporter.pass_check("Check1", "passed")
        mock_exit.side_effect = SystemExit
        with self.assertRaises(SystemExit):
            reporter.print_result("Test Target")
        mock_exit.assert_called_once_with(0)

    @mock.patch("sys.exit")
    def test_print_result_warn(self, mock_exit) -> None:
        reporter = DiagnosticReporter("Test")
        reporter.warn_check("Check1", "warning")
        mock_exit.side_effect = SystemExit
        with self.assertRaises(SystemExit):
            reporter.print_result("Test Target")
        mock_exit.assert_called_once_with(1)

    @mock.patch("sys.exit")
    def test_print_result_fail(self, mock_exit) -> None:
        reporter = DiagnosticReporter("Test")
        reporter.fail_check("Check1", "failure")
        mock_exit.side_effect = SystemExit
        with self.assertRaises(SystemExit):
            reporter.print_result("Test Target")
        mock_exit.assert_called_once_with(2)

    @mock.patch("subprocess.run")
    @mock.patch("shutil.which")
    def test_notify(self, mock_which, mock_run) -> None:
        reporter = DiagnosticReporter("Test")
        mock_which.side_effect = lambda c: "/bin/notify-send" if c == "notify-send" else None

        reporter.notify("Title", "Body")
        mock_run.assert_called_once_with(
            ["notify-send", "--app-name=KythOS", "Title", "Body"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @mock.patch("subprocess.run")
    @mock.patch("pathlib.Path.is_dir")
    @mock.patch("pathlib.Path.exists")
    @mock.patch("shutil.which")
    def test_run_health_checks_all_pass(self, mock_which, mock_exists, mock_is_dir, mock_run) -> None:
        mock_which.return_value = "/bin/dummy"
        mock_exists.return_value = True
        mock_is_dir.return_value = True
        mock_run.return_value = mock.Mock(returncode=0)

        reporter = DiagnosticReporter("Subsystem Health")
        run_health_checks(reporter)
        
        self.assertEqual(reporter.warnings, 0)
        self.assertEqual(reporter.failures, 0)
        check_names = [res[1] for res in reporter.results]
        self.assertIn("Kernel Scheduler", check_names)
        self.assertIn("Wine Synchronization", check_names)
        self.assertIn("Audio Stack", check_names)
        self.assertIn("Vulkan 3D Driver", check_names)
        self.assertIn("Video Codecs", check_names)
        self.assertIn("Input & Gamepads", check_names)

    @mock.patch("subprocess.run")
    @mock.patch("pathlib.Path.is_dir")
    @mock.patch("pathlib.Path.exists")
    @mock.patch("pathlib.Path.glob")
    @mock.patch("shutil.which")
    def test_run_health_checks_warnings(self, mock_which, mock_glob, mock_exists, mock_is_dir, mock_run) -> None:
        mock_which.return_value = None
        mock_exists.return_value = False
        mock_is_dir.return_value = False
        mock_glob.return_value = []
        mock_run.return_value = mock.Mock(returncode=1)

        reporter = DiagnosticReporter("Subsystem Health")
        run_health_checks(reporter)
        
        self.assertEqual(reporter.warnings, 4)
        self.assertEqual(reporter.failures, 0)

    @mock.patch("subprocess.Popen")
    @mock.patch("shutil.which")
    def test_create_github_issue_draft(self, mock_which, mock_popen) -> None:
        import os
        import tempfile
        from kyth_shared.diagnostics import create_github_issue_draft

        mock_which.return_value = "/usr/bin/xdg-open"
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, {"XDG_STATE_HOME": tmpdir}):
                draft_path, url = create_github_issue_draft(
                    title="Test Bug",
                    body="Something broke",
                    label="bug",
                    open_browser=True,
                )
                self.assertTrue(os.path.isfile(draft_path))
                self.assertIn("https://github.com/mrtrick37/kyth/issues/new?", url)
                self.assertIn("labels=bug", url)
                mock_popen.assert_called_once()


if __name__ == "__main__":
    unittest.main()

