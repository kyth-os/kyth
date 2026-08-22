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

    def test_snapshot_fsync_failure_keeps_recoverable_backup(self):
        journal = self._journal()
        with mock.patch("os.fsync", side_effect=OSError("sync unavailable")):
            journal._save_snapshot()
        self.assertTrue(journal._snapshot_saved)
        self.assertTrue((Path(journal._backup_dir.name) / "partition-table.backup").exists())
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

    def test_superseded_set_mountpoint_is_ignored_everywhere(self):
        # add_op() always appends — it never replaces an earlier pending
        # set_mountpoint for the same partition when the user changes a
        # mountpoint choice before committing (a completely normal WebUI
        # flow: pick a mountpoint, then pick a different one). Every reader
        # of self.ops must treat everything but each partition's LAST
        # set_mountpoint op as stale, or a user who reconsiders can get
        # blocked by a mountpoint they no longer have — or worse, commit()
        # can report the wrong partition as root after already repartitioning
        # the real disk (see _find_root_partition below).
        parts = [
            {"name": "/dev/sda1", "fstype": "ext4"},
            {"name": "/dev/sda2", "fstype": "btrfs"},
        ]
        journal = self._journal()
        # sda1 was first picked as root (ext4 — invalid for root), then
        # reconsidered to /home; sda2 (valid btrfs) is the REAL final root.
        journal.add_op("set_mountpoint", {"partition": "/dev/sda1", "mountpoint": "/"})
        journal.add_op("set_mountpoint", {"partition": "/dev/sda1", "mountpoint": "/home"})
        journal.add_op("set_mountpoint", {"partition": "/dev/sda2", "mountpoint": "/"})

        with mock.patch.object(journal_mod, "list_partitions", return_value=parts), \
             mock.patch.object(journal_mod, "_parent_disk", return_value="/dev/sda"):
            self.assertEqual(journal.validate(), [])
            self.assertEqual(journal._find_root_partition(), "/dev/sda2")

    def test_superseded_set_mountpoint_does_not_double_count_root(self):
        # Isolates the root-count/duplicate-mountpoint bookkeeping from the
        # btrfs-fstype check above by using two partitions of the same
        # filesystem — a stale "/" assignment must not make a later,
        # genuinely different partition's "/" look like a duplicate.
        parts = [
            {"name": "/dev/sda1", "fstype": "btrfs"},
            {"name": "/dev/sda2", "fstype": "btrfs"},
        ]
        journal = self._journal()
        journal.add_op("set_mountpoint", {"partition": "/dev/sda1", "mountpoint": "/"})
        journal.add_op("set_mountpoint", {"partition": "/dev/sda1", "mountpoint": "/home"})
        journal.add_op("set_mountpoint", {"partition": "/dev/sda2", "mountpoint": "/"})

        with mock.patch.object(journal_mod, "list_partitions", return_value=parts), \
             mock.patch.object(journal_mod, "_parent_disk", return_value="/dev/sda"):
            self.assertEqual(journal.validate(), [])
            self.assertEqual(journal._find_root_partition(), "/dev/sda2")

    def test_genuine_duplicate_root_assignment_is_still_rejected(self):
        # A real conflict (two partitions BOTH finally assigned "/") must
        # still be caught — the fix above must not weaken this check.
        parts = [
            {"name": "/dev/sda1", "fstype": "btrfs"},
            {"name": "/dev/sda2", "fstype": "btrfs"},
        ]
        journal = self._journal()
        journal.add_op("set_mountpoint", {"partition": "/dev/sda1", "mountpoint": "/"})
        journal.add_op("set_mountpoint", {"partition": "/dev/sda2", "mountpoint": "/"})

        with mock.patch.object(journal_mod, "list_partitions", return_value=parts), \
             mock.patch.object(journal_mod, "_parent_disk", return_value="/dev/sda"):
            errors = journal.validate()
        self.assertTrue(any("assigned more than once" in error for error in errors))

    def test_reconsidered_in_use_root_assignment_is_not_blocked(self):
        # _validate_not_in_use has the same stale-op class of bug: briefly
        # assigning "/" to a mounted/in-use partition, then reconsidering,
        # must not permanently block the commit over a choice that no
        # longer applies.
        parts = [
            {"name": "/dev/sda1", "fstype": "btrfs", "current": True},
            {"name": "/dev/sda2", "fstype": "btrfs"},
        ]
        journal = self._journal()
        journal.add_op("set_mountpoint", {"partition": "/dev/sda1", "mountpoint": "/"})
        journal.add_op("set_mountpoint", {"partition": "/dev/sda1", "mountpoint": "/data"})
        journal.add_op("set_mountpoint", {"partition": "/dev/sda2", "mountpoint": "/"})

        with mock.patch.object(journal_mod, "list_partitions", return_value=parts), \
             mock.patch.object(journal_mod, "_parent_disk", return_value="/dev/sda"):
            errors = journal.validate()
        self.assertEqual(errors, [])

    def test_in_use_partition_still_rejected_when_root_assignment_is_final(self):
        parts = [{"name": "/dev/sda1", "fstype": "btrfs", "current": True}]
        journal = self._journal()
        journal.add_op("set_mountpoint", {"partition": "/dev/sda1", "mountpoint": "/"})

        with mock.patch.object(journal_mod, "list_partitions", return_value=parts), \
             mock.patch.object(journal_mod, "_parent_disk", return_value="/dev/sda"):
            errors = journal.validate()
        self.assertTrue(any("currently mounted or in use" in error for error in errors))

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

    def test_gpt_table_requires_discoverable_bios_partition(self):
        journal = self._journal(dry_run=False)
        with (
            mock.patch.object(journal_mod, "list_partitions", return_value=[]),
            mock.patch.object(journal_mod, "_latest_partition_on_disk", return_value=None),
        ):
            with self.assertRaisesRegex(RuntimeError, "automatic BIOS boot partition"):
                journal._commit_new_table({"table_type": "gpt"}, mock.Mock())

        with (
            mock.patch.object(journal_mod, "list_partitions", return_value=[]),
            mock.patch.object(
                journal_mod, "_latest_partition_on_disk", return_value="/dev/sda1"
            ),
            mock.patch.object(journal_mod, "_partition_number", return_value=1),
        ):
            journal._commit_new_table({"table_type": "gpt"}, mock.Mock())
        journal._disk_service.set_partition_flag.assert_called_with(
            "/dev/sda", 1, "bios_grub"
        )

    def test_real_create_requires_discovery_and_formats_esp(self):
        journal = self._journal(dry_run=False)
        params = {
            "start_bytes": 1024**2,
            "size_bytes": 1024**3,
            "fs_type": "fat32",
            "label": "EFI",
            "mountpoint": "/boot/efi",
        }
        with (
            mock.patch.object(journal_mod, "list_partitions", return_value=[]),
            mock.patch.object(journal_mod, "_latest_partition_on_disk", return_value=None),
        ):
            with self.assertRaisesRegex(RuntimeError, "newly created partition"):
                journal._commit_create(dict(params), mock.Mock())

        with (
            mock.patch.object(journal_mod, "list_partitions", return_value=[]),
            mock.patch.object(
                journal_mod, "_latest_partition_on_disk", return_value="/dev/sda2"
            ),
            mock.patch.object(journal_mod, "_partition_number", return_value=2),
        ):
            journal._commit_create(params, mock.Mock())
        self.assertEqual(params["partition"], "/dev/sda2")
        journal._disk_service.format_filesystem.assert_called_with(
            "/dev/sda2", "fat32", "EFI"
        )
        journal._disk_service.set_partition_flag.assert_called_with("/dev/sda", 2, "esp")

    def test_real_resize_shrinks_filesystem_before_partition_boundary(self):
        journal = self._journal(dry_run=False)
        params = {"partition": "/dev/sda2", "new_size_bytes": 8 * 1024**3}
        with mock.patch.object(journal_mod, "list_partitions", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "was not found"):
                journal._commit_resize(params, mock.Mock())

        with (
            mock.patch.object(
                journal_mod, "list_partitions",
                return_value=[{"name": "/dev/sda2", "fstype": "ext4"}],
            ),
            mock.patch.object(journal_mod, "shrink_filesystem") as shrink,
            mock.patch.object(journal_mod, "_partition_number", return_value=2),
            mock.patch.object(journal_mod, "_partition_start_bytes", return_value=1024**2),
        ):
            journal._commit_resize(params, mock.Mock())
        shrink.assert_called_once_with("/dev/sda2", "ext4", 8 * 1024**3, mock.ANY)
        journal._disk_service.resize_partition.assert_called_once_with(
            "/dev/sda", 2, 1024**2, 8 * 1024**3
        )

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

    def _commit_failing_second_create(self, journal, first_ops):
        for op_kind, params in first_ops:
            journal.add_op(op_kind, params)
        journal.add_op("create", {
            "start_bytes": 4 * 1024**2,
            "size_bytes": 10 * 1024**3,
            "fs_type": "btrfs",
            "mountpoint": "/",
        })
        journal.add_op("create", {
            "start_bytes": 20 * 1024**3,
            "size_bytes": 1024**3,
            "fs_type": "fat32",
            "mountpoint": "/boot/efi",
        })
        journal._disk_service.create_partition.side_effect = [
            None,
            RuntimeError("parted failed creating EFI"),
        ]
        with (
            mock.patch(
                "kyth_installer.storage_guard.DiskLease",
                side_effect=lambda *a, **k: nullcontext(),
            ),
            mock.patch.object(journal, "_save_snapshot"),
        ):
            with self.assertRaisesRegex(RuntimeError, "parted failed"):
                journal.commit(mock.MagicMock())

    def test_commit_does_not_restore_gpt_after_format_following_new_table(self):
        # Manual wipe: new GPT + format root, then a later create fails.
        # Reloading the pre-commit table would name the old Windows/data
        # partitions over the mkfs'd region.
        journal = self._journal()
        self._commit_failing_second_create(journal, [
            ("new_table", {"table_type": "gpt"}),
        ])
        self.assertTrue(journal.irreversible_completed)
        journal._disk_service.restore_table.assert_not_called()

    def test_commit_does_not_restore_gpt_after_format_following_delete(self):
        journal = self._journal()
        self._commit_failing_second_create(journal, [
            ("delete", {"partition": "/dev/sda2"}),
        ])
        self.assertTrue(journal.irreversible_completed)
        journal._disk_service.restore_table.assert_not_called()

    def test_commit_restores_gpt_when_create_is_only_in_free_space(self):
        # No prior delete/new_table: the new filesystem sits in free space,
        # so reloading GPT just hides it. That undo is still correct.
        journal = self._journal()
        self._commit_failing_second_create(journal, [])
        self.assertFalse(journal.irreversible_completed)
        journal._disk_service.restore_table.assert_called_once()

    def test_commit_does_not_restore_gpt_when_shrink_succeeds_and_table_move_fails(self):
        journal = self._journal(dry_run=False)
        journal.add_op("resize", {"partition": "/dev/sda2", "new_size_bytes": 8 * 1024**3})
        journal._disk_service.resize_partition.side_effect = RuntimeError(
            "parted resizepart failed"
        )
        with (
            mock.patch(
                "kyth_installer.storage_guard.DiskLease",
                side_effect=lambda *a, **k: nullcontext(),
            ),
            mock.patch.object(journal, "_save_snapshot"),
            mock.patch.object(journal_mod, "_require_parted"),
            mock.patch.object(
                journal_mod, "list_partitions",
                return_value=[{"name": "/dev/sda2", "fstype": "ntfs"}],
            ),
            mock.patch.object(journal_mod, "shrink_filesystem") as shrink,
            mock.patch.object(journal_mod, "_partition_number", return_value=2),
            mock.patch.object(journal_mod, "_partition_start_bytes", return_value=1024**2),
        ):
            with self.assertRaisesRegex(RuntimeError, "resizepart"):
                journal.commit(mock.MagicMock())
        shrink.assert_called_once()
        self.assertTrue(journal.irreversible_completed)
        journal._disk_service.restore_table.assert_not_called()

    def test_rollback_refuses_after_irreversible_filesystem_op(self):
        journal = self._journal()
        journal.add_op("new_table", {})
        journal.irreversible_completed = True
        journal._snapshot_saved = True
        with mock.patch.object(journal, "_restore_snapshot") as restore:
            with self.assertRaisesRegex(RuntimeError, "would not restore files"):
                journal.rollback(mock.MagicMock())
        restore.assert_not_called()
        self.assertEqual(len(journal.ops), 1)

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

    def test_shim_fallbacks_cover_exception_and_original_paths(self):
        # Each _patched_* shim has an except Exception: pass + fallback import
        # Trigger the exception path by making the facade function raise
        with mock.patch("kyth_installer.partition_ops._parent_disk", side_effect=RuntimeError("facade boom")):
            # should fall back to disk._parent_disk without propagating
            with mock.patch("kyth_installer.disk._parent_disk", return_value="/dev/sda") as orig:
                self.assertEqual(journal_mod._patched_parent_disk("/dev/sda1"), "/dev/sda")
                orig.assert_called_once()
        with mock.patch("kyth_installer.partition_ops.list_disks", side_effect=RuntimeError("boom")):
            with mock.patch("kyth_installer.disk.list_disks", return_value=[{"name": "/dev/sda"}]) as orig:
                self.assertEqual(journal_mod._patched_list_disks(), [{"name": "/dev/sda"}])
        with mock.patch("kyth_installer.partition_ops.list_partitions", side_effect=RuntimeError("boom")):
            with mock.patch("kyth_installer.disk.list_partitions", return_value=[]) as orig:
                self.assertEqual(journal_mod._patched_list_partitions("/dev/sda"), [])
        with mock.patch("kyth_installer.partition_ops._partition_number", side_effect=RuntimeError("boom")):
            with mock.patch("kyth_installer.disk._partition_number", return_value=1) as orig:
                self.assertEqual(journal_mod._patched_partition_number("/dev/sda1"), 1)
        with mock.patch("kyth_installer.partition_ops._partition_start_bytes", side_effect=RuntimeError("boom")):
            with mock.patch("kyth_installer.disk._partition_start_bytes", return_value=1024) as orig:
                self.assertEqual(journal_mod._patched_partition_start_bytes("/dev/sda1"), 1024)
        with mock.patch("kyth_installer.partition_ops.shrink_filesystem", side_effect=RuntimeError("boom")):
            with mock.patch("kyth_installer.fsresize.shrink_filesystem", return_value=None) as orig:
                journal_mod._patched_shrink_filesystem("/dev/sda1", "ext4", 1024, log=mock.Mock())
                orig.assert_called_once()

    def test_journal_validation_covers_create_and_resize_error_branches(self):
        journal = self._journal()
        # invalid start/size (389)
        journal.clear()
        journal.add_op("create", {"start_bytes": -1, "size_bytes": -1, "fs_type": "btrfs"})
        errs = journal.validate()
        self.assertTrue(any("invalid start" in e for e in errs))
        # not present (427) and invalid new_size (432)
        journal.clear()
        journal.add_op("delete", {"partition": "/dev/sda9"})
        with mock.patch.object(journal_mod, "list_partitions", return_value=[{"name": "/dev/sda1"}]), mock.patch.object(journal_mod, "_parent_disk", return_value="/dev/sda"):
            errs = journal.validate()
            self.assertTrue(any("is not present" in e for e in errs))
        journal.clear()
        journal.add_op("resize", {"partition": "/dev/sda1", "new_size_bytes": 0})
        with mock.patch.object(journal_mod, "list_partitions", return_value=[{"name": "/dev/sda1"}]), mock.patch.object(journal_mod, "_parent_disk", return_value="/dev/sda"):
            errs = journal.validate()
            self.assertTrue(any("invalid new size" in e for e in errs))
        # mountpoint duplicate (460) — use non-overlapping regions so overlap doesn't mask duplicate
        journal.clear()
        journal.add_op("create", {"partition": "/dev/sda2", "mountpoint": "/home", "fs_type": "btrfs", "start_bytes": 1024**2, "size_bytes": 4 * 1024**3})
        journal.add_op("create", {"partition": "/dev/sda3", "mountpoint": "/home", "fs_type": "btrfs", "start_bytes": 8 * 1024**3, "size_bytes": 4 * 1024**3})
        with mock.patch.object(journal_mod, "list_partitions", return_value=[{"name": "/dev/sda1"}]), mock.patch.object(journal_mod, "_parent_disk", return_value="/dev/sda"):
            errs = journal.validate()
            self.assertTrue(any("assigned more than once" in e for e in errs))

    def test_journal_msdos_delete_and_commit_dispatch(self):
        # msdos delete and commit dispatch — use delete of a present partition without new_table reset
        # to hit 353-355 and 583/585/568 we use a simple delete+resize on a gpt disk
        journal = self._journal()
        journal.clear()
        journal.add_op("delete", {"partition": "/dev/sda2"})
        # make delete present: list_partitions contains sda2, parent returns sda
        with mock.patch.object(journal_mod, "list_partitions", return_value=[{"name": "/dev/sda1"}, {"name": "/dev/sda2"}]), mock.patch.object(journal_mod, "_parent_disk", return_value="/dev/sda"):
            errs = journal.validate()
            # may still have no-root error but should not have delete-not-present
            self.assertFalse(any("is not present" in e for e in errs))
        # delete commit with dry_run True (528-530) and commit dispatch (583,585,568)
        journal = self._journal(dry_run=True)
        journal.add_op("delete", {"partition": "/dev/sda1"})
        journal.add_op("resize", {"partition": "/dev/sda2", "new_size_bytes": 1024**3})
        # commit should dispatch delete and resize even in dry_run (uses 99 and mocked helpers)
        with mock.patch("kyth_installer.storage_guard.DiskLease", side_effect=lambda *a, **k: nullcontext()), mock.patch.object(journal, "_save_snapshot"), mock.patch.object(journal_mod, "list_partitions", return_value=[{"name": "/dev/sda1"}, {"name": "/dev/sda2"}]), mock.patch.object(journal_mod, "_partition_number", return_value=1), mock.patch.object(journal_mod, "_partition_start_bytes", return_value=0), mock.patch.object(journal_mod, "shrink_filesystem"):
            journal.commit(mock.Mock())
            self.assertTrue(journal.committed)
            journal._disk_service.delete_partition.assert_called()
            journal._disk_service.resize_partition.assert_called()
        # non-dry_run commit must call _require_parted (568)
        journal2 = self._journal(dry_run=False)
        journal2.add_op("delete", {"partition": "/dev/sda1"})
        with mock.patch("kyth_installer.storage_guard.DiskLease", side_effect=lambda *a, **k: nullcontext()), mock.patch.object(journal2, "_save_snapshot"), mock.patch.object(journal_mod, "list_partitions", return_value=[{"name": "/dev/sda1"}]), mock.patch.object(journal_mod, "_partition_number", return_value=1), mock.patch.object(journal_mod, "_require_parted") as req:
            journal2.commit(mock.Mock())
            req.assert_called()

    def test_journal_save_snapshot_requires_sgdisk_and_handles_missing_backup(self):
        journal = self._journal(dry_run=False)
        # save snapshot when not dry_run must call _require_sgdisk (154)
        with mock.patch.object(journal_mod, "_require_sgdisk") as req, mock.patch.object(journal, "_discard_snapshot"):
            journal._save_snapshot()
            req.assert_called()
        # restore without backup dir returns early (185)
        journal = self._journal(dry_run=False)
        journal._snapshot_saved = True
        journal._backup_dir = None
        with mock.patch.object(journal_mod, "_require_sgdisk"):
            journal._restore_snapshot()
            journal._disk_service.restore_table.assert_not_called()
        # _find_root_partition returns None when no root (238)
        journal = self._journal()
        self.assertIsNone(journal._find_root_partition())


if __name__ == "__main__":
    unittest.main()
