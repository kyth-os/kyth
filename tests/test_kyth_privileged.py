import importlib.machinery
import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("kyth_privileged", str(ROOT / "build_files/kyth-privileged"))
SPEC = importlib.util.spec_from_loader("kyth_privileged", LOADER)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PrivilegedProtocolTests(unittest.TestCase):
    def test_only_named_operations_produce_argv(self):
        op, argv, stdin = MODULE.validate_request({"operation": "kernel_switch", "flavor": "cachy"})
        self.assertEqual(op, "kernel_switch")
        self.assertEqual(argv, ["/usr/bin/ujust", "switch-kernel", "cachy"])
        self.assertIsNone(stdin)

    def test_rejects_arbitrary_command_and_kernel_flavor(self):
        with self.assertRaises(ValueError):
            MODULE.validate_request({"operation": "run", "argv": ["/bin/sh"]})
        with self.assertRaises(ValueError):
            MODULE.validate_request({"operation": "kernel_switch", "flavor": "../../etc"})

    def test_bitlocker_key_never_enters_argv(self):
        op, argv, key = MODULE.validate_request({"operation": "bitlocker_unlock", "device": "/dev/sda3", "key": "12345678"})
        self.assertEqual(op, "bitlocker_unlock")
        self.assertNotIn(key, argv)
        self.assertEqual(argv[-1], "/dev/stdin")

    @patch.object(MODULE.subprocess, "run")
    def test_run_operation_uses_fixed_command(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, stdout="updated", stderr="")
        op, detail = MODULE.run_operation({"operation": "firmware_update"})
        self.assertEqual((op, detail), ("firmware_update", "updated"))
        self.assertEqual(run.call_args.args[0], ["/usr/bin/fwupdmgr", "update"])
        self.assertEqual(run.call_args.kwargs["timeout"], 900)

    def test_network_share_uses_fixed_helper_and_peer_identity(self):
        request = {
            "operation": "network_share_add",
            "payload": {
                "name": "media", "server": "nas.local", "share_path": "media",
                "mount_point": "/mnt/media", "username": "pat", "password": "not-in-argv",
                "domain": "", "auto_mount": True, "mount_now": False, "uid": 0, "gid": 0,
            },
        }
        op, argv, stdin = MODULE.validate_request(request, caller_uid=1000, caller_gid=1001)
        self.assertEqual(op, "network_share_add")
        self.assertEqual(argv, ["/usr/libexec/kyth-network-share", "add"])
        self.assertNotIn("not-in-argv", argv)
        payload = json.loads(stdin)
        self.assertEqual((payload["uid"], payload["gid"]), (1000, 1001))
        self.assertEqual(payload["password"], "not-in-argv")

    def test_network_share_rejects_unsafe_mount_point(self):
        with self.assertRaises(ValueError):
            MODULE.validate_request({"operation": "network_share_remove", "payload": {"name": "media", "mount_point": "/etc/kyth"}})


if __name__ == "__main__":
    unittest.main()
