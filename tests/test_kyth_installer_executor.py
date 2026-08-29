"""Focused tests for the explicit privileged executor boundary."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
# This module is new in the source tree and may not exist in a stale local
# build_files mirror; use the source package for this focused boundary test.
sys.path.insert(0, str(ROOT / "src" / "kyth_shared"))
sys.path.insert(0, str(ROOT / "src" / "kyth-installer"))

from kyth_installer.executor import ExecutorCommand, PrivilegedExecutor  # noqa: E402


class InstallerExecutorTests(unittest.TestCase):
    def test_run_applies_root_boundary_and_operation_metadata(self):
        run = mock.Mock(return_value=SimpleNamespace(returncode=0))
        executor = PrivilegedExecutor(
            run_command=run,
            as_root=lambda argv: ["sudo", "-n", *argv],
        )
        command = ExecutorCommand.from_argv(
            ["bootc", "status", "--json"],
            "read bootc status",
            timeout=5,
        )

        result = executor.run(command, capture_output=True, text=True)

        self.assertEqual(result.returncode, 0)
        run.assert_called_once_with(
            ["sudo", "-n", "bootc", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
            description="read bootc status",
        )

    def test_stream_uses_typed_command_and_does_not_accept_shell_text(self):
        stream = mock.Mock()
        runner_factory = mock.Mock(return_value=stream)
        executor = PrivilegedExecutor(
            run_command=mock.Mock(),
            as_root=lambda argv: ["root", *argv],
            stream_runner_factory=runner_factory,
        )
        command = ExecutorCommand.from_argv(
            ["bootc", "install", "to-disk", "/dev/sda"],
            "install image",
        )

        executor.stream(
            command,
            rx_bytes=lambda: 0,
            publish=lambda _event: None,
            pct_start=5,
            pct_end=90,
            log=lambda _message: None,
            progress=lambda _value: None,
            absolute_timeout=None,
        )

        runner_factory.assert_called_once()
        self.assertEqual(
            stream.run.call_args.args[:3],
            (["root", "bootc", "install", "to-disk", "/dev/sda"], 5, 90),
        )
        with self.assertRaises(ValueError):
            ExecutorCommand.from_argv([], "empty operation")
        with self.assertRaises(TypeError):
            ExecutorCommand.from_argv("bootc install", "shell text")

    def test_unprivileged_command_can_be_explicitly_requested(self):
        run = mock.Mock(return_value=SimpleNamespace(returncode=0))
        executor = PrivilegedExecutor(
            run_command=run,
            as_root=lambda argv: ["sudo", "-n", *argv],
        )

        executor.run(
            ExecutorCommand.from_argv(
                ["chromium", "--version"],
                "inspect browser",
                as_root=False,
            )
        )

        run.assert_called_once_with(
            ["chromium", "--version"],
            timeout=30,
            description="inspect browser",
        )


if __name__ == "__main__":
    unittest.main()
