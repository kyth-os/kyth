from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.commands import (  # noqa: E402
    CommandRunner,
    command_stdout,
    normalize_command,
    run_optional,
    run_text,
)


class CommandRunnerTests(unittest.TestCase):
    def test_normalize_command_accepts_paths(self) -> None:
        self.assertEqual(
            normalize_command(["tool", pathlib.Path("/tmp/value")]),
            ["tool", "/tmp/value"],
        )

    def test_normalize_command_rejects_shell_strings(self) -> None:
        with self.assertRaises(TypeError):
            normalize_command("tool --flag")

    def test_normalize_command_rejects_empty_commands(self) -> None:
        with self.assertRaises(ValueError):
            normalize_command([])

    @mock.patch("subprocess.run")
    def test_run_defaults_to_non_raising_exit_handling(self, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(["tool"], 2)

        result = CommandRunner().run(["tool"])

        self.assertEqual(result.returncode, 2)
        mock_run.assert_called_once_with(["tool"], check=False)

    @mock.patch("subprocess.run", side_effect=FileNotFoundError)
    def test_optional_returns_none_for_missing_executable(self, _mock_run) -> None:
        self.assertIsNone(run_optional(["missing-tool"]))

    @mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["tool"], 1))
    def test_text_returns_none_for_timeout(self, _mock_run) -> None:
        self.assertIsNone(run_text(["tool"], timeout=1))

    @mock.patch("subprocess.run")
    def test_text_captures_decoded_output(self, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            ["tool"],
            0,
            stdout="value\n",
            stderr="",
        )

        result = run_text(["tool"], timeout=3)

        self.assertIsNotNone(result)
        self.assertEqual(result.stdout, "value\n")
        mock_run.assert_called_once_with(
            ["tool"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )

    @mock.patch("subprocess.run")
    def test_command_stdout_strips_by_default(self, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            ["tool"],
            0,
            stdout=" value \n",
            stderr="",
        )

        self.assertEqual(command_stdout(["tool"]), "value")


if __name__ == "__main__":
    unittest.main()
