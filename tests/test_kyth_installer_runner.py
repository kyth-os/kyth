import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer.runner import InstallerCommand, run_command, run_installer_command  # noqa: E402


class InstallerRunnerTests(unittest.TestCase):
    @mock.patch("kyth_installer.runner.subprocess.run")
    def test_run_command_normalizes_args_and_logs_command(self, mock_run):
        messages = []
        mock_run.return_value = subprocess.CompletedProcess(["true"], 0)

        result = run_command(["echo", Path("/tmp/example")], log=messages.append)

        self.assertEqual(result.returncode, 0)
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args.args[0], ["echo", "/tmp/example"])
        self.assertEqual(messages, ["$ echo /tmp/example"])

    @mock.patch("kyth_installer.runner.subprocess.run")
    def test_run_installer_command_forwards_timeout(self, mock_run):
        command = InstallerCommand(
            argv=("bootc", "install", "to-filesystem"),
            description="install image",
            timeout=1800,
        )

        run_installer_command(command)

        self.assertEqual(mock_run.call_args.kwargs["timeout"], 1800)

    @mock.patch("kyth_installer.runner.subprocess.run")
    def test_checked_failure_gets_context(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=2,
            cmd=["mkfs.btrfs"],
            output="mkfs failed",
        )

        with self.assertRaisesRegex(RuntimeError, "format root failed"):
            run_command(["mkfs.btrfs"], description="format root failed", check=True)

    @mock.patch("kyth_installer.runner.subprocess.run")
    def test_non_checked_failure_returns_process(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(["false"], 1)

        result = run_command(["false"])

        self.assertEqual(result.returncode, 1)
        mock_run.assert_called_once_with(["false"], timeout=None)

    @mock.patch("kyth_installer.runner.subprocess.run")
    def test_timeout_gets_context(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["partprobe"],
            timeout=30,
        )

        with self.assertRaisesRegex(RuntimeError, "timed out"):
            run_command(["partprobe"], timeout=30)


if __name__ == "__main__":
    unittest.main()
