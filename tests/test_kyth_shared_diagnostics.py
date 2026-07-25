"""Unit tests for the shared diagnostics module."""
from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.diagnostics import DiagnosticReporter


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


if __name__ == "__main__":
    unittest.main()
