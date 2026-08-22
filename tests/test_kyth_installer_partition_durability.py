"""Mid-phase durability for destructive partition commits.

The coarse transaction statuses used to jump from "prepared" straight to
"image_installed" across the whole storage phase, so a power loss between
mkpart and mkfs used to leave no record of how far the wipe got. Storage now
records "storage_complete" only after the image write; these tests still pin
the per-op bracketing and the fsync ordering that make the mid-wipe record
survive.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer import recovery  # noqa: E402
from kyth_installer.context import InstallerContext  # noqa: E402
from kyth_installer.partition_ops_journal import Journal  # noqa: E402
from kyth_installer.recovery import (  # noqa: E402
    read_transaction_state,
    write_transaction_state,
)


class FakeDiskService:
    """Disk service that records calls instead of touching hardware."""

    dry_run = True

    def __init__(self, fail_on: str = "") -> None:
        self.calls: list[str] = []
        self.fail_on = fail_on

    def _note(self, name: str) -> None:
        self.calls.append(name)
        if name == self.fail_on:
            raise RuntimeError(f"simulated failure in {name}")

    def backup_table(self, _disk, backup):
        Path(backup).write_text("table", encoding="utf-8")

    def restore_table(self, _disk, _backup):
        self._note("restore_table")

    def create_label(self, _disk, _table_type):
        self._note("create_label")

    def create_unformatted_partition(self, *_args):
        self._note("create_unformatted_partition")

    def set_partition_flag(self, *_args):
        self._note("set_partition_flag")

    def create_partition(self, *_args):
        self._note("create_partition")

    def format_filesystem(self, *_args):
        self._note("format_filesystem")

    def delete_partition(self, *_args):
        self._note("delete_partition")


def build_journal(fail_on: str = "") -> tuple[Journal, FakeDiskService]:
    service = FakeDiskService(fail_on=fail_on)
    with mock.patch(
        "kyth_installer.partition_ops_journal._normal_device_path",
        return_value="/dev/sda",
    ):
        journal = Journal("/dev/sda", disk_service=service)
    return journal, service


@mock.patch.dict("os.environ", {"KYTH_INSTALL_ALLOW_NO_DISK_LOCK": "1"}, clear=False)
class PartitionStepBracketingTests(unittest.TestCase):
    def test_each_destructive_op_is_bracketed(self):
        journal, _service = build_journal()
        journal.add_op("create", {
            "start_bytes": 1024**2,
            "size_bytes": 1024**3,
            "fs_type": "btrfs",
            "mountpoint": "/",
        })
        steps: list[tuple[str, str, str]] = []

        journal.commit(lambda _msg: None, record=lambda *args: steps.append(args))

        self.assertEqual(
            [("create", "started", "/dev/sda"), ("create", "completed", "/dev/sdap99")],
            steps,
        )

    def test_in_flight_op_is_left_marked_started(self):
        """The power-loss signature: a step that never got its completion."""
        journal, _service = build_journal(fail_on="format_filesystem")
        journal.add_op("create", {
            "start_bytes": 1024**2,
            "size_bytes": 1024**3,
            "fs_type": "btrfs",
            "mountpoint": "/",
        })
        steps: list[tuple[str, str, str]] = []

        with self.assertRaises(RuntimeError):
            journal.commit(lambda _msg: None, record=lambda *args: steps.append(args))

        self.assertEqual([("create", "started", "/dev/sda")], steps)
        self.assertFalse(any(status == "completed" for _kind, status, _target in steps))

    def test_metadata_only_ops_are_not_recorded_as_destructive(self):
        journal, _service = build_journal()
        journal.add_op("create", {
            "start_bytes": 1024**2,
            "size_bytes": 1024**3,
            "fs_type": "btrfs",
            "mountpoint": "/",
        })
        journal.add_op("set_mountpoint", {"partition": "/dev/sda1", "mountpoint": "/home"})
        steps: list[tuple[str, str, str]] = []

        journal.commit(lambda _msg: None, record=lambda *args: steps.append(args))

        self.assertNotIn("set_mountpoint", {kind for kind, _status, _target in steps})

    def test_commit_without_a_recorder_still_works(self):
        journal, service = build_journal()
        journal.add_op("new_table", {"table_type": "gpt"})

        journal.commit(lambda _msg: None)

        self.assertIn("create_label", service.calls)

    def test_recorder_failure_never_aborts_a_live_commit(self):
        """Bookkeeping must not destroy a disk mid-partition."""
        journal, service = build_journal()
        journal.add_op("new_table", {"table_type": "gpt"})

        def explode(*_args):
            raise OSError("read-only transaction report")

        journal.commit(lambda _msg: None, record=explode)

        self.assertTrue(journal.committed)
        self.assertIn("create_label", service.calls)


class TransactionStatePersistenceTests(unittest.TestCase):
    def test_partition_steps_reach_the_transaction_report(self):
        context = InstallerContext()
        context.record_partition_step("create", "started", "/dev/sda")
        context.record_partition_step("create", "completed", "/dev/sda1")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transaction.json"
            write_transaction_state(path, context=context, status="partitioning")
            payload = json.loads(path.read_text())

        self.assertEqual(2, len(payload["partition_steps"]))
        self.assertEqual("started", payload["partition_steps"][0]["status"])
        self.assertEqual("/dev/sda1", payload["partition_steps"][1]["target"])

    def test_report_survives_reread(self):
        context = InstallerContext()
        context.record_partition_step("format", "started", "/dev/sda2")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transaction.json"
            write_transaction_state(path, context=context, status="partitioning")
            restored = read_transaction_state(path)

        self.assertEqual("partitioning", restored["status"])
        self.assertEqual("format", restored["partition_steps"][0]["kind"])

    def test_steps_reset_between_transactions(self):
        from kyth_installer.context import InstallLifecycle
        from kyth_installer.context_types import InstallRequest

        context = InstallerContext()
        context.record_partition_step("create", "completed", "/dev/sda1")
        context.transition(InstallLifecycle.FAILED)

        context.replace_request(InstallRequest.from_state(context.state))

        self.assertEqual([], context.partition_steps)


class FsyncOrderingTests(unittest.TestCase):
    def test_parent_directory_is_fsynced_after_the_rename(self):
        """Fsyncing before the replace flushes a directory without the new name."""
        events: list[str] = []
        real_replace = recovery.os.replace

        def traced_replace(src, dst):
            events.append("replace")
            return real_replace(src, dst)

        def traced_fsync_dir(_path):
            events.append("fsync_dir")

        context = InstallerContext()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transaction.json"
            with (
                mock.patch.object(recovery.os, "replace", traced_replace),
                mock.patch.object(recovery, "_fsync_directory", traced_fsync_dir),
            ):
                write_transaction_state(path, context=context, status="started")

        self.assertEqual(["replace", "fsync_dir"], events)

    def test_failure_summary_uses_the_same_ordering(self):
        events: list[str] = []
        real_replace = recovery.os.replace

        def traced_replace(src, dst):
            events.append("replace")
            return real_replace(src, dst)

        context = InstallerContext()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "failure.json"
            with (
                mock.patch.object(recovery.os, "replace", traced_replace),
                mock.patch.object(
                    recovery, "_fsync_directory", lambda _p: events.append("fsync_dir")
                ),
            ):
                recovery.write_failure_summary(path, context=context, message="boom")

        self.assertEqual(["replace", "fsync_dir"], events)

    def test_payload_is_fsynced_before_the_rename(self):
        context = InstallerContext()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transaction.json"
            with mock.patch.object(
                recovery.os, "fsync", wraps=recovery.os.fsync
            ) as fsync:
                write_transaction_state(path, context=context, status="started")

            self.assertTrue(fsync.called)
            self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
