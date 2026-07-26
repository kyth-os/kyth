import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer.context import InstallLifecycle, InstallerContext, InstallPhase
from kyth_installer.recovery import cleanup_registered_mounts, write_failure_summary


class InstallerRecoveryTests(unittest.TestCase):
    def test_cleanup_runs_in_reverse_order_and_clears_registry(self):
        context = InstallerContext()
        context.register_mount("/target")
        context.register_mount("/target/boot/efi")
        run = MagicMock()

        cleanup_registered_mounts(context, run=run)

        self.assertIn("/target/boot/efi", run.call_args_list[0].args[0])
        self.assertIn("/target", run.call_args_list[1].args[0])
        self.assertEqual(context.cleanup_mounts, [])

    def test_failure_summary_records_phase_without_secrets(self):
        context = InstallerContext()
        context.state.update({
            "disk": "/dev/sda",
            "install_mode": "wipe",
            "password_hash": "sensitive",
            "mok_password": "sensitive",
        })
        context.transition(InstallLifecycle.FAILED)
        context.enter_phase(InstallPhase.IMAGE)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "failure.json"
            write_failure_summary(path, context=context, message="bootc failed")
            payload = json.loads(path.read_text())

        self.assertEqual(payload["phase"], "image")
        self.assertEqual(payload["message"], "bootc failed")
        self.assertNotIn("password_hash", payload)
        self.assertNotIn("mok_password", payload)


if __name__ == "__main__":
    unittest.main()
