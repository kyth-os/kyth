import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer.runner import (  # noqa: E402
    InstallerCommand,
    run_command,
    run_installer_command,
    spawn_command,
)


class InstallerRunnerTests(unittest.TestCase):
    @mock.patch("kyth_installer.runner.subprocess.run")
    def test_run_command_normalizes_args_and_logs_command(self, mock_run):
        messages = []
        mock_run.return_value = subprocess.CompletedProcess(["true"], 0)

        result = run_command(["echo", Path("/tmp/example")], log=messages.append)  # noqa: S108 — fixture string, not a real path opened on disk

        self.assertEqual(result.returncode, 0)
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args.args[0], ["echo", "/tmp/example"])  # noqa: S108 — fixture string, not a real path opened on disk
        self.assertFalse(mock_run.call_args.kwargs["shell"])
        self.assertEqual(messages, ["$ echo /tmp/example"])

    def test_run_command_rejects_shell_strings_and_shell_execution(self):
        with self.assertRaises(TypeError):
            run_command("echo unsafe")
        with self.assertRaisesRegex(ValueError, "shell execution is forbidden"):
            run_command(["echo", "safe"], shell=True)  # noqa: S604 — asserts this is rejected, never executed

    def test_run_command_rejects_unapproved_executables(self):
        with self.assertRaisesRegex(RuntimeError, "unapproved installer executable"):
            run_command(["python3", "-c", "print('unsafe')"])
        with self.assertRaisesRegex(RuntimeError, "outside trusted system paths"):
            run_command(["/tmp/lsblk"])  # noqa: S108 — intentionally untrusted fixture path

    def test_run_command_validates_executable_nested_under_sudo(self):
        with self.assertRaisesRegex(RuntimeError, "unapproved installer executable"):
            run_command(["sudo", "-n", "python3", "-c", "print('unsafe')"])
        with self.assertRaisesRegex(RuntimeError, "unsupported sudo command form"):
            run_command(["sudo", "--preserve-env", "lsblk"])

    @mock.patch("kyth_installer.runner.subprocess.Popen")
    def test_spawn_command_accepts_installer_chromium_sudo_form(self, mock_popen):
        spawn_command([
            "sudo", "-u", "liveuser", "env", "DISPLAY=:0", "chromium", "--app=http://127.0.0.1",
        ])

        mock_popen.assert_called_once_with(
            ["sudo", "-u", "liveuser", "env", "DISPLAY=:0", "chromium", "--app=http://127.0.0.1"],
            shell=False,
        )

    @mock.patch("kyth_installer.runner.subprocess.Popen")
    def test_spawn_command_uses_the_same_validated_boundary(self, mock_popen):
        spawn_command(["echo", Path("message")], stdout=subprocess.PIPE)

        mock_popen.assert_called_once_with(
            ["echo", "message"], shell=False, stdout=subprocess.PIPE
        )
        with self.assertRaises(TypeError):
            spawn_command("echo unsafe")
        with self.assertRaisesRegex(ValueError, "shell execution is forbidden"):
            spawn_command(["echo", "safe"], shell=True)

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
        mock_run.assert_called_once_with(["false"], timeout=30, shell=False, check=False)

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
