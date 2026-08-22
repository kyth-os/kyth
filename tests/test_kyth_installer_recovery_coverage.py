import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer.context import InstallerContext
from kyth_installer.recovery import (  # noqa: E402
    read_transaction_state,
    rescue_guidance,
    write_failure_summary,
    write_transaction_state,
)


class RecoveryDurabilityCoverageTests(unittest.TestCase):
    """Cover the fsync(dir) + symlink/ownership + JSON error branches that
    dropped recovery.py from 85.0% to 83.6% after the durability hardening."""

    def test_failure_summary_fsync_dir_branch(self):
        ctx = InstallerContext()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "failure.json"
            write_failure_summary(path, context=ctx, message="test")
            # exercises stream.flush/fsync + dir fsync (lines 61-62) + 120-121 equivalent
            self.assertTrue(path.exists())
            data = json.loads(path.read_text())
            self.assertEqual(data["message"], "test")

    def test_transaction_durability_flushes(self):
        ctx = InstallerContext()
        ctx.state.update({"disk": "/dev/sda", "install_mode": "wipe"})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tx.json"
            write_transaction_state(path, context=ctx, status="prepared")
            # hits stream.flush/fsync + dir fsync (lines 62-63, 120-121)
            payload = read_transaction_state(path)
            self.assertEqual(payload["status"], "prepared")

    def test_transaction_refuses_symlink_parent(self):
        ctx = InstallerContext()
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real"
            real.mkdir()
            link = Path(tmp) / "link"
            link.symlink_to(real)
            p = link / "tx.json"
            with self.assertRaises(RuntimeError):
                write_transaction_state(p, context=ctx, status="x")  # covers 98,100

    def test_read_broken_json_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text("{ not json")
            self.assertEqual(read_transaction_state(p), {})  # covers 132-133
            self.assertEqual(read_transaction_state(Path(tmp) / "missing.json"), {})  # covers 129
            # symlink file also returns {}
            link = Path(tmp) / "link.json"
            link.symlink_to(p)
            self.assertEqual(read_transaction_state(link), {})

    def test_read_symlink_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target.json"
            target.write_text('{"status":"ok"}')
            link = Path(tmp) / "link.json"
            link.symlink_to(target)
            # read_transaction_state guards is_symlink -> {} (line 129)
            self.assertEqual(read_transaction_state(link), {})

    def test_rescue_guidance_treats_legacy_image_installed_as_unbootable(self):
        guide = rescue_guidance({"status": "image_installed"})
        self.assertFalse(guide["bootable"])
        self.assertEqual(guide["severity"], "unbootable")
        self.assertIn("configure", guide["message"].lower())

    def test_rescue_guidance_splits_storage_and_configure(self):
        self.assertFalse(rescue_guidance({"status": "storage_complete"})["bootable"])
        self.assertFalse(rescue_guidance({"status": "configure_started"})["bootable"])
        self.assertFalse(rescue_guidance({"status": "configure_complete"})["bootable"])
        self.assertTrue(rescue_guidance({"status": "secure_boot_staged"})["bootable"])
        self.assertTrue(rescue_guidance({"status": "complete"})["bootable"])

    def test_install_worker_records_split_durable_statuses(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "kyth-installer"
            / "kyth_installer"
            / "phases"
            / "run.py"
        ).read_text(encoding="utf-8")
        for status in (
            "storage_complete",
            "configure_started",
            "configure_complete",
            "secure_boot_staged",
            "complete",
        ):
            self.assertIn(f'_record_transaction(context, "{status}"', source)
        self.assertNotIn('_record_transaction(context, "image_installed"', source)


if __name__ == "__main__":
    unittest.main()
