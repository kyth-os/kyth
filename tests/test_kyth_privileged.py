import importlib.machinery
import importlib.util
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


if __name__ == "__main__":
    unittest.main()
