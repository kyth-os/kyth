"""Behavioral tests for the Python KythOS daily-driver smoke check."""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.smoke_check import SmokeCheck


class SmokeCheckTests(unittest.TestCase):
    def test_results_retain_their_section(self) -> None:
        checker = SmokeCheck()
        with mock.patch("builtins.print"):
            checker.section("Hardware")
            checker.warn("GPU", "not found")
        self.assertEqual(checker.results[0].section, "Hardware")
        self.assertEqual(checker.results[0].level, "WARN")

    def test_failure_always_returns_two(self) -> None:
        checker = SmokeCheck()
        with mock.patch("builtins.print"):
            checker.fail("Required", "missing")
            self.assertEqual(checker.exit_code(strict=False), 2)
            self.assertEqual(checker.exit_code(strict=True), 2)

    def test_warning_only_fails_in_strict_mode(self) -> None:
        checker = SmokeCheck()
        with mock.patch("builtins.print"):
            checker.warn("Optional", "missing")
            self.assertEqual(checker.exit_code(strict=False), 0)
            self.assertEqual(checker.exit_code(strict=True), 1)

    def test_path_absence_check(self) -> None:
        checker = SmokeCheck()
        with (
            mock.patch("pathlib.Path.exists", return_value=False),
            mock.patch("builtins.print"),
        ):
            checker.check_path("/missing", "Removed path", absent=True)
        self.assertEqual(checker.results[0].level, "PASS")

    def test_optional_command_is_warning(self) -> None:
        checker = SmokeCheck()
        with (
            mock.patch("shutil.which", return_value=None),
            mock.patch("builtins.print"),
        ):
            checker.check_command("optional", "Optional", optional=True)
        self.assertEqual(checker.results[0].level, "WARN")


if __name__ == "__main__":
    unittest.main()
