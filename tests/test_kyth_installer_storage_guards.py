from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer.mount_registry import MountRegistry  # noqa: E402
from kyth_installer.storage_guard import DiskLease, PartitionTableGuard  # noqa: E402


class DiskLeaseTests(unittest.TestCase):
    @mock.patch("kyth_installer.storage_guard.os.close")
    @mock.patch("kyth_installer.storage_guard.fcntl.flock")
    @mock.patch("kyth_installer.storage_guard.os.open", return_value=41)
    def test_exclusive_lease_locks_logs_and_unlocks(self, opened, flock, closed):
        log = mock.Mock()
        with DiskLease("/dev/sda", log):
            pass

        opened.assert_called_once_with("/dev/sda", mock.ANY)
        self.assertEqual(flock.call_args_list[0], mock.call(41, mock.ANY))
        self.assertEqual(flock.call_args_list[-1], mock.call(41, mock.ANY))
        self.assertIn("exclusive lock", log.call_args_list[0].args[0])
        closed.assert_called_once_with(41)

    @mock.patch("kyth_installer.storage_guard.os.close")
    @mock.patch("kyth_installer.storage_guard.fcntl.flock")
    @mock.patch("kyth_installer.storage_guard.os.open", return_value=7)
    def test_shared_lease_uses_shared_lock(self, _opened, flock, _closed):
        with DiskLease("/dev/sdb", mock.Mock(), exclusive=False):
            pass
        self.assertEqual(flock.call_args_list[0].args[1] & 1, 1)

    @mock.patch("kyth_installer.storage_guard.os.close")
    @mock.patch("kyth_installer.storage_guard.fcntl.flock", side_effect=BlockingIOError)
    @mock.patch("kyth_installer.storage_guard.os.open", return_value=12)
    def test_busy_disk_fails_closed_and_still_closes_fd(self, _opened, _flock, closed):
        with self.assertRaisesRegex(RuntimeError, "Another process is using /dev/sda"):
            with DiskLease("/dev/sda", mock.Mock()):
                self.fail("busy lease must not enter guarded body")
        closed.assert_called_once_with(12)

    @mock.patch("kyth_installer.storage_guard.os.open", side_effect=PermissionError("denied"))
    def test_unavailable_advisory_lock_warns_and_continues(self, _opened):
        log = mock.Mock()
        entered = False
        with DiskLease("/dev/sda", log):
            entered = True
        self.assertTrue(entered)
        self.assertIn("could not hold lock", log.call_args.args[0])

    @mock.patch("kyth_installer.storage_guard.os.close", side_effect=OSError("close failed"))
    @mock.patch("kyth_installer.storage_guard.fcntl.flock")
    @mock.patch("kyth_installer.storage_guard.os.open", return_value=9)
    def test_cleanup_errors_do_not_mask_body_error(self, _opened, flock, _closed):
        flock.side_effect = [None, OSError("unlock failed")]
        with self.assertRaisesRegex(ValueError, "body failed"):
            with DiskLease("/dev/sda", mock.Mock()):
                raise ValueError("body failed")

    def test_runtime_error_wrapped_as_oserror_is_reraised(self):
        # line 38: outer OSError handler must re-raise a RuntimeError that is also an OSError
        class Both(OSError, RuntimeError):
            pass

        with mock.patch("kyth_installer.storage_guard.os.open", side_effect=Both("both")):
            with self.assertRaises(Both):
                with DiskLease("/dev/sda", mock.Mock()):
                    self.fail("must not enter body when open fails with Both")

    def test_partition_guard_uses_lazy_disk_service(self):
        # lines 64,66: when disk_service is None, lazily construct DiskService
        service = mock.Mock()

        def backup(_disk, path):
            pathlib.Path(path).write_bytes(b"lazy table")

        service.backup_table.side_effect = backup
        with mock.patch("kyth_installer.services.disk_service.DiskService", return_value=service) as ctor:
            log = mock.Mock()
            with PartitionTableGuard("/dev/sda", log, disk_service=None) as backup_path:
                self.assertTrue(pathlib.Path(backup_path).is_file())
            ctor.assert_called_once()
            service.backup_table.assert_called_once()


class PartitionTableGuardTests(unittest.TestCase):
    def _service(self, *, restore_error: Exception | None = None):
        service = mock.Mock()

        def backup(_disk, path):
            pathlib.Path(path).write_bytes(b"partition table")

        service.backup_table.side_effect = backup
        if restore_error is not None:
            service.restore_table.side_effect = restore_error
        return service

    def test_successful_guard_makes_durable_backup_without_restore(self):
        service = self._service()
        log = mock.Mock()
        with PartitionTableGuard("/dev/sda", log, disk_service=service) as backup:
            self.assertTrue(pathlib.Path(backup).is_file())
            self.assertEqual(pathlib.Path(backup).read_bytes(), b"partition table")

        service.backup_table.assert_called_once()
        service.restore_table.assert_not_called()
        self.assertIn("Backing up", log.call_args_list[0].args[0])

    def test_body_failure_restores_snapshot_and_reraises(self):
        service = self._service()
        log = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "partition failed"):
            with PartitionTableGuard("/dev/nvme0n1", log, disk_service=service) as backup:
                raise RuntimeError("partition failed")

        service.restore_table.assert_called_once_with("/dev/nvme0n1", backup)
        self.assertTrue(any("restored" in call.args[0] for call in log.call_args_list))

    def test_restore_failure_is_logged_without_masking_original_error(self):
        service = self._service(restore_error=OSError("restore failed"))
        log = mock.Mock()
        with self.assertRaisesRegex(ValueError, "original failure"):
            with PartitionTableGuard("/dev/sda", log, disk_service=service):
                raise ValueError("original failure")
        self.assertTrue(any("restore failed" in call.args[0] for call in log.call_args_list))

    def test_fsync_failure_warns_but_guard_remains_usable(self):
        service = self._service()
        log = mock.Mock()
        with mock.patch("kyth_installer.storage_guard.os.fsync", side_effect=OSError("no sync")):
            with PartitionTableGuard("/dev/sda", log, disk_service=service):
                pass
        self.assertTrue(any("could not fsync" in call.args[0] for call in log.call_args_list))

    def test_backup_failure_prevents_guarded_operation(self):
        service = mock.Mock()
        service.backup_table.side_effect = OSError("backup failed")
        entered = False
        with self.assertRaisesRegex(OSError, "backup failed"):
            with PartitionTableGuard("/dev/sda", mock.Mock(), disk_service=service):
                entered = True
        self.assertFalse(entered)
        service.restore_table.assert_not_called()


class MountRegistryTests(unittest.TestCase):
    def test_register_is_idempotent_and_release_is_safe(self):
        registry = MountRegistry()
        registry.register("/target")
        registry.register("/target")
        registry.register("/target/boot")
        self.assertEqual(registry.snapshot(), ["/target", "/target/boot"])
        registry.release("/missing")
        registry.release("/target")
        self.assertEqual(registry.snapshot(), ["/target/boot"])
        registry.clear()
        self.assertEqual(registry.snapshot(), [])

    @mock.patch("kyth_installer.system._safe_umount")
    def test_hold_registers_then_unmounts_and_releases(self, unmount):
        registry = MountRegistry()
        run = mock.Mock()
        with registry.hold("/target", run=run):
            self.assertEqual(registry.snapshot(), ["/target"])
        unmount.assert_called_once_with(run, "/target", check=True)
        self.assertEqual(registry.snapshot(), [])

    def test_hold_without_runner_only_releases(self):
        registry = MountRegistry()
        with registry.hold("/target"):
            self.assertEqual(registry.snapshot(), ["/target"])
        self.assertEqual(registry.snapshot(), [])

    @mock.patch("kyth_installer.system._safe_umount", side_effect=OSError("busy"))
    def test_hold_logs_unmount_failure_and_releases(self, _unmount):
        registry = MountRegistry()
        log = mock.Mock()
        with registry.hold("/target", run=mock.Mock(), log=log):
            pass
        self.assertEqual(registry.snapshot(), [])
        self.assertIn("could not unmount /target", log.call_args.args[0])

    @mock.patch("kyth_installer.system._safe_umount")
    def test_cleanup_is_lifo_and_continues_after_failure(self, unmount):
        registry = MountRegistry()
        for path in ("/target", "/target/boot", "/target/boot/efi"):
            registry.register(path)
        unmount.side_effect = [None, OSError("busy"), None]
        log = mock.Mock()
        run = mock.Mock()

        registry.cleanup(run=run, log=log)

        self.assertEqual(
            [call.args[1] for call in unmount.call_args_list],
            ["/target/boot/efi", "/target/boot", "/target"],
        )
        self.assertEqual(registry.snapshot(), [])
        self.assertIn("could not unmount /target/boot", log.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
