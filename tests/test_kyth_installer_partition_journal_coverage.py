import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer import partition_ops  # noqa: E402
from kyth_installer import partition_ops_journal as journal_mod  # noqa: E402
from kyth_installer.context import InstallerContext  # noqa: E402


class InstallerPartitionJournalCoverageTests(unittest.TestCase):
    def _journal(self, *, dry_run=True):
        service = mock.MagicMock(dry_run=dry_run)
        service.backup_table.side_effect = lambda _disk, path: Path(path).write_bytes(b"table")
        with mock.patch.object(journal_mod, "_normal_device_path", side_effect=lambda value: value):
            return journal_mod.Journal("/dev/sda", disk_service=service)

    def test_journal_rejects_invalid_disk_and_exposes_queue_safely(self):
        with mock.patch.object(journal_mod, "_normal_device_path", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Invalid disk path"):
                journal_mod.Journal("bad", disk_service=mock.MagicMock())
        journal = self._journal()
        original = {"table_type": "gpt"}
        op = journal.add_op("new_table", original)
        original["table_type"] = "msdos"
        self.assertEqual(op["params"]["table_type"], "gpt")
        self.assertEqual(journal.pending(), [op])
        self.assertFalse(journal.remove_op(4))
        self.assertTrue(journal.remove_op(0))

    def test_tool_requirements_report_missing_binaries_and_filesystems(self):
        with mock.patch.object(journal_mod.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "sgdisk"):
                journal_mod._require_sgdisk()
            with self.assertRaisesRegex(RuntimeError, "parted"):
                journal_mod._require_parted()
            with self.assertRaisesRegex(RuntimeError, "not available"):
                journal_mod._require_mkfs("btrfs")
        with self.assertRaisesRegex(RuntimeError, "Unsupported filesystem"):
            journal_mod._require_mkfs("unknown")

    def test_snapshot_save_restore_and_discard_are_idempotent(self):
        journal = self._journal()
        journal._save_snapshot()
        self.assertTrue(journal._snapshot_saved)
        backup = Path(journal._backup_dir.name) / "partition-table.backup"
        self.assertTrue(backup.exists())
        journal._restore_snapshot()
        journal._disk_service.restore_table.assert_called_once()
        self.assertFalse(journal._snapshot_saved)
        self.assertIsNone(journal._backup_dir)
        journal._discard_snapshot()

    def test_restore_without_snapshot_or_backup_is_safe(self):
        journal = self._journal(dry_run=False)
        journal._restore_snapshot()
        journal._disk_service.restore_table.assert_not_called()
        journal._snapshot_saved = True
        backup_dir = mock.MagicMock()
        backup_dir.name = "/definitely/missing"
        journal._backup_dir = backup_dir
        with mock.patch.object(journal_mod, "_require_sgdisk"):
            journal._restore_snapshot()
        journal._disk_service.restore_table.assert_not_called()
        backup_dir.cleanup.assert_called_once()

    def test_root_partition_prefers_created_root_then_existing_assignment(self):
        journal = self._journal()
        journal.add_op("create", {"mountpoint": "/", "partition": "/dev/sda3"})
        self.assertEqual(journal._find_root_partition(), "/dev/sda3")
        journal.clear()
        journal.add_op("set_mountpoint", {"mountpoint": "/", "partition": "/dev/sda2"})
        with mock.patch.object(journal_mod, "list_partitions", return_value=[{"name": "/dev/sda2"}]):
            self.assertEqual(journal._find_root_partition(), "/dev/sda2")

    def test_commit_create_dry_run_records_root_and_skips_swap_format(self):
        journal = self._journal()
        params = {
            "start_bytes": 1024**2,
            "size_bytes": 8 * 1024**3,
            "fs_type": "linux-swap",
            "mountpoint": "/",
        }
        journal._commit_create(params, mock.MagicMock())
        self.assertEqual(params["partition"], "/dev/sdap99")
        journal._disk_service.create_partition.assert_called_once()
        journal._disk_service.format_filesystem.assert_not_called()

    def test_commit_dispatches_metadata_and_format_operations(self):
        journal = self._journal()
        journal.add_op("format", {"partition": "/dev/sda2", "fs_type": "btrfs", "label": "ROOT"})
        journal.add_op("set_mountpoint", {"partition": "/dev/sda2", "mountpoint": "/"})
        with mock.patch("kyth_installer.storage_guard.DiskLease", side_effect=lambda *a, **k: nullcontext()), mock.patch.object(
            journal, "_save_snapshot"
        ), mock.patch.object(journal_mod, "list_partitions", return_value=[{"name": "/dev/sda2"}]):
            root = journal.commit(mock.MagicMock())
        self.assertEqual(root, "/dev/sda2")
        self.assertTrue(journal.committed)
        journal._disk_service.format_filesystem.assert_called_once_with("/dev/sda2", "btrfs", "ROOT")

    def test_invalid_commit_helpers_fail_before_disk_mutation(self):
        journal = self._journal()
        with self.assertRaisesRegex(RuntimeError, "invalid start"):
            journal._commit_create({"start_bytes": 0, "size_bytes": 1}, mock.MagicMock())
        with self.assertRaisesRegex(RuntimeError, "no partition"):
            journal._commit_delete({}, mock.MagicMock())
        with self.assertRaisesRegex(RuntimeError, "invalid partition"):
            journal._commit_resize({}, mock.MagicMock())
        with self.assertRaisesRegex(RuntimeError, "no partition"):
            journal._commit_format({}, mock.MagicMock())

    def test_rollback_without_snapshot_clears_ops_and_with_snapshot_resets_state(self):
        journal = self._journal()
        journal.add_op("new_table", {})
        log = mock.MagicMock()
        journal.rollback(log)
        self.assertEqual(journal.pending(), [])
        self.assertIn("No partition snapshot", log.call_args.args[0])

        journal.add_op("new_table", {})
        journal._snapshot_saved = True
        journal._committed = True
        journal._root_partition = "/dev/sda2"
        with mock.patch.object(journal, "_restore_snapshot") as restore:
            journal.rollback(log)
        restore.assert_called_once()
        self.assertFalse(journal.committed)
        self.assertIsNone(journal.root_partition)

    def test_partition_facade_builds_labels_and_resets_existing_journal(self):
        self.assertEqual(partition_ops._mkfs_cmd("unknown", "/dev/sda1"), [])
        fat = partition_ops._mkfs_cmd("fat32", "/dev/sda1", "EFI")
        self.assertEqual(fat[-3:], ["-n", "EFI", "/dev/sda1"])
        btrfs = partition_ops._mkfs_cmd("btrfs", "/dev/sda2", "ROOT")
        self.assertEqual(btrfs[-3:], ["-L", "ROOT", "/dev/sda2"])

        context = InstallerContext()
        old = SimpleNamespace(
            ops=[{"kind": "x"}], _committed=True, _root_partition="/dev/sda1",
            _discard_snapshot=mock.MagicMock(),
        )
        context.journal = old
        partition_ops.reset_journal(context)
        self.assertEqual(old.ops, [])
        self.assertFalse(old._committed)
        self.assertIsNone(old._root_partition)
        old._discard_snapshot.assert_called_once()
        self.assertIsNone(context.journal)


if __name__ == "__main__":
    unittest.main()
