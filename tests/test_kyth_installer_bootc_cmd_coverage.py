import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer.phases import bootc_cmd  # noqa: E402


class InstallerBootcCommandCoverageTests(unittest.TestCase):
    def test_filesystem_command_includes_destructive_ack_flags_and_target(self):
        with patch.object(bootc_cmd, "SKIP_FETCH_CHECK", False):
            command = bootc_cmd._build_bootc_install_cmd(
                "to-filesystem",
                "docker://source",
                "docker://target",
                "/mnt/root",
                ["--root-ssh-authorized-keys", "/tmp/keys"],
            )
        self.assertEqual(command[:3], ["bootc", "install", "to-filesystem"])
        self.assertIn("--acknowledge-destructive", command)
        self.assertEqual(command[-3:], ["--root-ssh-authorized-keys", "/tmp/keys", "/mnt/root"])

    def test_disk_command_adds_skip_fetch_once(self):
        with patch.object(bootc_cmd, "SKIP_FETCH_CHECK", True):
            command = bootc_cmd._build_bootc_install_cmd(
                "to-disk", "source", "target", "/dev/sda", ["--skip-fetch-check"]
            )
            added = bootc_cmd._build_bootc_install_cmd(
                "to-disk", "source", "target", "/dev/sdb"
            )
        self.assertEqual(command.count("--skip-fetch-check"), 1)
        self.assertEqual(added[-2:], ["--skip-fetch-check", "/dev/sdb"])
        self.assertNotIn("--acknowledge-destructive", command)

    @patch("kyth_installer.install._as_root", side_effect=lambda argv: ["root", *argv])
    @patch.object(bootc_cmd, "get_rx_bytes", return_value=42)
    @patch.object(bootc_cmd, "StreamingCommandRunner")
    def test_run_command_forwards_safety_controls(self, runner_type, rx_bytes, _as_root):
        runner = runner_type.return_value
        publish = MagicMock()
        cancel = object()
        log = MagicMock()
        progress = MagicMock()
        bootc_cmd._run_cmd(
            ["bootc", "install"],
            10,
            80,
            log,
            progress,
            stall_timeout=30,
            absolute_timeout=90,
            publish=publish,
            cancel_event=cancel,
            io_stall_timeout=15,
            net_stall_timeout=20,
        )
        runner_type.assert_called_once_with(rx_bytes=rx_bytes, publish=publish)
        args, kwargs = runner.run.call_args
        self.assertEqual(args[:3], (["root", "bootc", "install"], 10, 80))
        self.assertEqual(kwargs["stall_timeout"], 30)
        self.assertEqual(kwargs["absolute_timeout"], 90)
        self.assertIs(kwargs["cancel_event"], cancel)
        self.assertEqual(kwargs["io_stall_timeout"], 15)
        self.assertEqual(kwargs["net_stall_timeout"], 20)

    @patch("kyth_installer.install._as_root", side_effect=lambda argv: ["root", *argv])
    @patch.object(bootc_cmd, "get_rx_bytes", return_value=42)
    @patch.object(bootc_cmd, "StreamingCommandRunner")
    def test_typed_request_handoff_uses_rust_execution_helper(self, runner_type, _rx_bytes, _as_root):
        runner = runner_type.return_value
        request = {
            "subcommand": "to-disk",
            "source_imgref": "oci:/usr/share/kyth/image:latest",
            "target_imgref": "ghcr.io/kyth-os/kyth:testing",
            "target": "/dev/sda",
            "skip_fetch_check": True,
            "wipe": True,
        }

        bootc_cmd._run_cmd(
            ["bootc", "install", "to-disk"],
            5,
            90,
            MagicMock(),
            MagicMock(),
            execution_request=request,
        )

        args, kwargs = runner.run.call_args
        self.assertEqual(args[0], ["root", "kyth-installer-exec", "--operation", "stream"])
        self.assertEqual(
            json.loads(kwargs["stdin_data"]),
            {"kind": "bootc_install", "request": request},
        )

    @patch("kyth_installer.install._as_root", side_effect=lambda argv: argv)
    @patch.object(bootc_cmd, "StreamingCommandRunner")
    def test_error_factory_classifies_network_and_generic_failures(self, runner_type, _as_root):
        bootc_cmd._run_cmd(["bootc"], 0, 100, MagicMock(), MagicMock())
        error_factory = runner_type.return_value.run.call_args.kwargs["error_factory"]

        network = error_factory(1, ["TLS handshake timeout"], ["bootc", "install"])
        self.assertIsInstance(network, RuntimeError)
        self.assertIn("network", str(network).lower())

        generic = error_factory(7, ["first", "fatal detail"], ["bootc", "install"])
        self.assertIn("exit 7", str(generic))
        self.assertIn("bootc install", str(generic))
        self.assertIn("fatal detail", str(generic))

        empty = error_factory(2, [], ["bootc"])
        self.assertIn("No command output was captured", str(empty))


if __name__ == "__main__":
    unittest.main()
