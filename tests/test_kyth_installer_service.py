import sys
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files/kyth-installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from kyth_installer import partition_ops
from kyth_installer import context as context_module
from kyth_installer.context import InstallerContext
from kyth_installer.services.installer_service import InstallerService
from kyth_installer.app import _load_answer_file, run_headless


class TestInstallerService(unittest.TestCase):
    def setUp(self):
        self.context = InstallerContext()
        self.service = InstallerService(self.context)

    @patch("kyth_installer.disk.list_disks")
    def test_new_table(self, mock_list_disks):
        mock_list_disks.return_value = [{"name": "/dev/sda"}]
        body = {"disk": "/dev/sda", "table_type": "gpt"}

        # Test valid disk and table type
        res = self.service.new_table(body)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("pending"), 1)
        
        # Test invalid disk
        body_invalid = {"disk": "/dev/sdb", "table_type": "gpt"}
        res_invalid = self.service.new_table(body_invalid)
        self.assertFalse(res_invalid.get("ok"))

        self.assertFalse(self.service.new_table({})["ok"])
        self.assertFalse(
            self.service.new_table({"disk": "/dev/sda", "table_type": "invalid"})["ok"]
        )

    @patch("kyth_installer.disk.list_disks")
    @patch("kyth_installer.system.list_timezones")
    def test_start_install_validations(self, mock_timezones, mock_list_disks):
        mock_list_disks.return_value = [{"name": "/dev/sda"}]
        mock_timezones.return_value = ["UTC", "America/New_York"]
        
        # Invalid username
        body = {
            "disk": "/dev/sda",
            "install_mode": "wipe",
            "username": "INVALID USERNAME",
            "password": "password",
            "hostname": "kyth",
            "confirm_backup": True,
            "confirm_erase": True,
        }
        res = self.service.start_install(body)
        self.assertFalse(res.get("started"))

        # Invalid hostname
        body["username"] = "validuser"
        body["hostname"] = "invalid_hostname_!!!"
        res = self.service.start_install(body)
        self.assertFalse(res.get("started"))

    @patch("kyth_installer.disk.list_disks")
    def test_remove_pending_drops_the_targeted_op_only(self, mock_list_disks):
        mock_list_disks.return_value = [{"name": "/dev/sda"}]
        self.service.new_table({"disk": "/dev/sda", "table_type": "gpt"})
        res = self.service.create_partition({
            # Starts past the 1 MiB automatic BIOS boot partition new_table
            # reserves on GPT disks, so this doesn't overlap it.
            "disk": "/dev/sda", "start_bytes": 4 * 1024**2, "size_bytes": 10 * 1024**3,
            "fs_type": "btrfs", "mountpoint": "/",
        })
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("pending"), 2)

        remove_res = self.service.remove_pending({"disk": "/dev/sda", "index": 1})
        self.assertTrue(remove_res.get("ok"))
        self.assertEqual(remove_res.get("pending"), 1)
        journal = partition_ops.get_journal(self.context)
        self.assertEqual(journal.ops[0]["kind"], "new_table")

        bad_res = self.service.remove_pending({"disk": "/dev/sda", "index": 99})
        self.assertFalse(bad_res.get("ok"))
        self.assertEqual(len(journal.ops), 1)

    @patch("kyth_installer.disk.list_disks")
    def test_remove_pending_rejects_after_commit(self, mock_list_disks):
        mock_list_disks.return_value = [{"name": "/dev/sda"}]
        self.service.new_table({"disk": "/dev/sda", "table_type": "gpt"})
        journal = partition_ops.get_journal(self.context)
        journal._committed = True

        res = self.service.remove_pending({"disk": "/dev/sda", "index": 0})
        self.assertFalse(res.get("ok"))
        self.assertEqual(len(journal.ops), 1)


class InstallerServiceCrudTests(unittest.TestCase):
    """create/delete/resize/format/set_mountpoint/commit/rollback/reboot,
    plus the _journal_for/_partition_for error branches they all share."""

    def setUp(self):
        self.context = InstallerContext()
        self.service = InstallerService(self.context)

    def _new_table(self, mock_list_disks):
        mock_list_disks.return_value = [{"name": "/dev/sda"}]
        res = self.service.new_table({"disk": "/dev/sda", "table_type": "gpt"})
        self.assertTrue(res.get("ok"))

    # ── _journal_for / _partition_for error branches ───────────────────

    def test_journal_for_requires_a_disk(self):
        res = self.service.create_partition({})
        self.assertFalse(res.get("ok"))
        self.assertIn("No disk specified", res.get("message", ""))

    def test_journal_for_requires_an_active_journal(self):
        res = self.service.create_partition({"disk": "/dev/sda"})
        self.assertFalse(res.get("ok"))
        self.assertIn("No active partition journal", res.get("message", ""))

    @patch("kyth_installer.disk.list_disks")
    def test_partition_for_requires_a_partition(self, mock_list_disks):
        self._new_table(mock_list_disks)
        res = self.service.delete_partition({"disk": "/dev/sda"})
        self.assertFalse(res.get("ok"))

    @patch("kyth_installer.disk.list_disks")
    def test_partition_for_propagates_native_target_validation_error(self, mock_list_disks):
        self._new_table(mock_list_disks)
        journal = partition_ops.get_journal(self.context)
        journal.rust_validate_target = MagicMock(return_value="native target rejected")
        result = self.service._partition_for({"disk": "/dev/sda", "partition": "/dev/sda1"})
        self.assertEqual(result[3], {"ok": False, "message": "native target rejected"})

    @patch("kyth_installer.disk._parent_disk")
    @patch("kyth_installer.disk.list_disks")
    def test_partition_for_rejects_a_partition_from_another_disk(self, mock_list_disks, mock_parent):
        self._new_table(mock_list_disks)
        mock_parent.return_value = "/dev/sdb"
        res = self.service.delete_partition({"disk": "/dev/sda", "partition": "/dev/sdb1"})
        self.assertFalse(res.get("ok"))
        self.assertIn("does not belong to the active disk", res.get("message", ""))

    # ── create_partition ─────────────────────────────────────────────

    @patch("kyth_installer.disk.list_disks")
    def test_create_partition_rejects_invalid_geometry(self, mock_list_disks):
        self._new_table(mock_list_disks)
        res = self.service.create_partition({
            "disk": "/dev/sda", "start_bytes": -1, "size_bytes": 0, "fs_type": "btrfs",
        })
        self.assertFalse(res.get("ok"))
        self.assertIn("Invalid start offset or size", res.get("message", ""))

    @patch("kyth_installer.disk.list_disks")
    def test_create_partition_rejects_unsupported_filesystem(self, mock_list_disks):
        self._new_table(mock_list_disks)
        res = self.service.create_partition({
            "disk": "/dev/sda", "start_bytes": 4 * 1024**2, "size_bytes": 10 * 1024**3,
            "fs_type": "zfs",
        })
        self.assertFalse(res.get("ok"))
        self.assertIn("Unsupported filesystem", res.get("message", ""))

    # ── delete_partition ─────────────────────────────────────────────

    @patch("kyth_installer.disk.list_partitions")
    @patch("kyth_installer.disk._parent_disk")
    @patch("kyth_installer.disk.list_disks")
    def test_delete_partition_not_found(self, mock_list_disks, mock_parent, mock_list_parts):
        self._new_table(mock_list_disks)
        mock_parent.return_value = "/dev/sda"
        mock_list_parts.return_value = []
        res = self.service.delete_partition({"disk": "/dev/sda", "partition": "/dev/sda1"})
        self.assertFalse(res.get("ok"))
        self.assertIn("not found", res.get("message", ""))

    @patch("kyth_installer.disk.list_partitions")
    @patch("kyth_installer.disk._parent_disk")
    @patch("kyth_installer.disk.list_disks")
    def test_delete_partition_rejects_mounted_partition(self, mock_list_disks, mock_parent, mock_list_parts):
        self._new_table(mock_list_disks)
        mock_parent.return_value = "/dev/sda"
        mock_list_parts.return_value = [{"name": "/dev/sda1", "current": True}]
        res = self.service.delete_partition({"disk": "/dev/sda", "partition": "/dev/sda1"})
        self.assertFalse(res.get("ok"))
        self.assertIn("mounted or in-use", res.get("message", ""))

    @patch("kyth_installer.disk.list_partitions")
    @patch("kyth_installer.disk._parent_disk")
    @patch("kyth_installer.disk.list_disks")
    def test_delete_partition_success(self, mock_list_disks, mock_parent, mock_list_parts):
        self._new_table(mock_list_disks)
        mock_parent.return_value = "/dev/sda"
        mock_list_parts.return_value = [{"name": "/dev/sda1", "current": False, "in_use": False}]
        res = self.service.delete_partition({"disk": "/dev/sda", "partition": "/dev/sda1"})
        self.assertTrue(res.get("ok"))
        journal = partition_ops.get_journal(self.context)
        self.assertEqual(journal.ops[-1]["kind"], "delete")

    # ── resize_partition ─────────────────────────────────────────────

    @patch("kyth_installer.disk.list_partitions")
    @patch("kyth_installer.disk._parent_disk")
    @patch("kyth_installer.disk.list_disks")
    def test_resize_partition_requires_a_new_size(self, mock_list_disks, mock_parent, mock_list_parts):
        self._new_table(mock_list_disks)
        mock_parent.return_value = "/dev/sda"
        res = self.service.resize_partition({
            "disk": "/dev/sda", "partition": "/dev/sda1", "new_size_bytes": 0,
        })
        self.assertFalse(res.get("ok"))
        self.assertIn("new size is required", res.get("message", ""))

    @patch("kyth_installer.disk.list_partitions")
    @patch("kyth_installer.disk._parent_disk")
    @patch("kyth_installer.disk.list_disks")
    def test_resize_partition_not_found(self, mock_list_disks, mock_parent, mock_list_parts):
        self._new_table(mock_list_disks)
        mock_parent.return_value = "/dev/sda"
        mock_list_parts.return_value = []
        res = self.service.resize_partition({
            "disk": "/dev/sda", "partition": "/dev/sda1", "new_size_bytes": 1024,
        })
        self.assertFalse(res.get("ok"))
        self.assertIn("not found", res.get("message", ""))

    @patch("kyth_installer.disk.list_partitions")
    @patch("kyth_installer.disk._parent_disk")
    @patch("kyth_installer.disk.list_disks")
    def test_resize_partition_rejects_growing_the_partition(self, mock_list_disks, mock_parent, mock_list_parts):
        self._new_table(mock_list_disks)
        mock_parent.return_value = "/dev/sda"
        mock_list_parts.return_value = [{"name": "/dev/sda1", "size_bytes": 10 * 1024**3}]
        res = self.service.resize_partition({
            "disk": "/dev/sda", "partition": "/dev/sda1", "new_size_bytes": 20 * 1024**3,
        })
        self.assertFalse(res.get("ok"))
        self.assertIn("smaller than current size", res.get("message", ""))

    @patch("kyth_installer.disk.list_partitions")
    @patch("kyth_installer.disk._parent_disk")
    @patch("kyth_installer.disk.list_disks")
    def test_resize_partition_success(self, mock_list_disks, mock_parent, mock_list_parts):
        self._new_table(mock_list_disks)
        mock_parent.return_value = "/dev/sda"
        mock_list_parts.return_value = [{"name": "/dev/sda1", "size_bytes": 10 * 1024**3}]
        res = self.service.resize_partition({
            "disk": "/dev/sda", "partition": "/dev/sda1", "new_size_bytes": 5 * 1024**3,
        })
        self.assertTrue(res.get("ok"))
        journal = partition_ops.get_journal(self.context)
        self.assertEqual(journal.ops[-1]["kind"], "resize")

    # ── format_partition ─────────────────────────────────────────────

    @patch("kyth_installer.disk._parent_disk")
    @patch("kyth_installer.disk.list_disks")
    def test_format_partition_rejects_unsupported_filesystem(self, mock_list_disks, mock_parent):
        self._new_table(mock_list_disks)
        mock_parent.return_value = "/dev/sda"
        res = self.service.format_partition({
            "disk": "/dev/sda", "partition": "/dev/sda1", "fs_type": "zfs",
        })
        self.assertFalse(res.get("ok"))
        self.assertIn("Unsupported filesystem", res.get("message", ""))

    @patch("kyth_installer.disk._parent_disk")
    @patch("kyth_installer.disk.list_disks")
    def test_format_partition_success(self, mock_list_disks, mock_parent):
        self._new_table(mock_list_disks)
        mock_parent.return_value = "/dev/sda"
        res = self.service.format_partition({
            "disk": "/dev/sda", "partition": "/dev/sda1", "fs_type": "btrfs",
        })
        self.assertTrue(res.get("ok"))
        journal = partition_ops.get_journal(self.context)
        self.assertEqual(journal.ops[-1]["kind"], "format")

    # ── set_mountpoint ───────────────────────────────────────────────

    @patch("kyth_installer.disk._parent_disk")
    @patch("kyth_installer.disk.list_disks")
    def test_set_mountpoint_rejects_relative_path(self, mock_list_disks, mock_parent):
        self._new_table(mock_list_disks)
        mock_parent.return_value = "/dev/sda"
        res = self.service.set_mountpoint({
            "disk": "/dev/sda", "partition": "/dev/sda1", "mountpoint": "home",
        })
        self.assertFalse(res.get("ok"))
        self.assertIn("absolute path", res.get("message", ""))

    @patch("kyth_installer.disk._parent_disk")
    @patch("kyth_installer.disk.list_disks")
    def test_set_mountpoint_accepts_swap(self, mock_list_disks, mock_parent):
        self._new_table(mock_list_disks)
        mock_parent.return_value = "/dev/sda"
        res = self.service.set_mountpoint({
            "disk": "/dev/sda", "partition": "/dev/sda1", "mountpoint": "swap",
        })
        self.assertTrue(res.get("ok"))

    @patch("kyth_installer.disk._parent_disk")
    @patch("kyth_installer.disk.list_disks")
    def test_set_mountpoint_accepts_absolute_path(self, mock_list_disks, mock_parent):
        self._new_table(mock_list_disks)
        mock_parent.return_value = "/dev/sda"
        res = self.service.set_mountpoint({
            "disk": "/dev/sda", "partition": "/dev/sda1", "mountpoint": "/home",
        })
        self.assertTrue(res.get("ok"))
        journal = partition_ops.get_journal(self.context)
        self.assertEqual(journal.ops[-1]["kind"], "set_mountpoint")

    # ── commit_partitions / rollback_partitions ─────────────────────

    def _committable_journal(self, mock_list_disks):
        self._new_table(mock_list_disks)
        res = self.service.create_partition({
            "disk": "/dev/sda", "start_bytes": 4 * 1024**2, "size_bytes": 10 * 1024**3,
            "fs_type": "btrfs", "mountpoint": "/",
        })
        self.assertTrue(res.get("ok"))
        return partition_ops.get_journal(self.context)

    @patch("kyth_installer.disk.list_disks")
    def test_commit_partitions_reports_validation_errors(self, mock_list_disks):
        self._new_table(mock_list_disks)  # no create op -> no root partition
        res = self.service.commit_partitions({"disk": "/dev/sda"})
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("message"), "Validation failed.")
        self.assertTrue(res.get("errors"))

    @patch("kyth_installer.disk.list_disks")
    def test_commit_partitions_success_transitions_back_to_idle(self, mock_list_disks):
        journal = self._committable_journal(mock_list_disks)
        with patch.object(journal, "commit", return_value="/dev/sda1") as mock_commit:
            res = self.service.commit_partitions({"disk": "/dev/sda"})
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("root_partition"), "/dev/sda1")
        mock_commit.assert_called_once()
        self.assertEqual(self.context.lifecycle, context_module.InstallLifecycle.IDLE)

    @patch("kyth_installer.disk.list_disks")
    def test_commit_partitions_rolls_back_on_failure(self, mock_list_disks):
        journal = self._committable_journal(mock_list_disks)
        with patch.object(journal, "commit", side_effect=RuntimeError("sgdisk failed")), \
             patch.object(journal, "rollback") as mock_rollback:
            res = self.service.commit_partitions({"disk": "/dev/sda"})
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("message"), "sgdisk failed")
        mock_rollback.assert_called_once()
        # IDLE, not FAILED: journal.rollback() already restored the partition
        # table, so nothing unsafe remains and the WebUI's Commit button (which
        # the frontend re-enables on this exact error path) must be able to
        # retry — see test_commit_partitions_can_be_retried_after_a_failure.
        self.assertEqual(self.context.lifecycle, context_module.InstallLifecycle.IDLE)

    @patch("kyth_installer.disk.list_disks")
    def test_commit_partitions_can_be_retried_after_a_failure(self, mock_list_disks):
        journal = self._committable_journal(mock_list_disks)
        with patch.object(journal, "commit", side_effect=RuntimeError("sgdisk failed")), \
             patch.object(journal, "rollback"):
            failed = self.service.commit_partitions({"disk": "/dev/sda"})
        self.assertFalse(failed.get("ok"))

        # The frontend re-enables its Commit button on exactly this failure
        # and expects a retry (e.g. of a transient sgdisk hiccup) to actually
        # attempt the commit again, not bounce off an internal FSM error.
        with patch.object(journal, "commit", return_value="/dev/sda1") as mock_commit:
            retried = self.service.commit_partitions({"disk": "/dev/sda"})
        self.assertTrue(retried.get("ok"), retried.get("message"))
        self.assertEqual(retried.get("root_partition"), "/dev/sda1")
        mock_commit.assert_called_once()
        self.assertEqual(self.context.lifecycle, context_module.InstallLifecycle.IDLE)

    @patch("kyth_installer.disk.list_disks")
    def test_commit_partitions_fails_closed_after_irreversible_op(self, mock_list_disks):
        journal = self._committable_journal(mock_list_disks)
        journal.irreversible_completed = True
        with patch.object(journal, "commit", side_effect=RuntimeError("mkfs of later op failed")), \
             patch.object(journal, "rollback") as mock_rollback:
            res = self.service.commit_partitions({"disk": "/dev/sda"})
        self.assertFalse(res.get("ok"))
        self.assertTrue(res.get("irreversible"))
        self.assertIn("would not restore files", res.get("message"))
        mock_rollback.assert_not_called()
        self.assertEqual(self.context.lifecycle, context_module.InstallLifecycle.FAILED)

    @patch("kyth_installer.disk.list_disks")
    def test_rollback_partitions_success_resets_the_journal(self, mock_list_disks):
        journal = self._committable_journal(mock_list_disks)
        with patch.object(journal, "rollback") as mock_rollback:
            res = self.service.rollback_partitions({"disk": "/dev/sda"})
        self.assertTrue(res.get("ok"))
        mock_rollback.assert_called_once()
        self.assertIsNone(partition_ops.get_journal(self.context))

    @patch("kyth_installer.disk.list_disks")
    def test_rollback_partitions_reports_runtime_error(self, mock_list_disks):
        journal = self._committable_journal(mock_list_disks)
        with patch.object(journal, "rollback", side_effect=RuntimeError("sgdisk restore failed")):
            res = self.service.rollback_partitions({"disk": "/dev/sda"})
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("message"), "sgdisk restore failed")

    def test_partition_actions_return_missing_journal_error_consistently(self):
        body = {"disk": "/dev/sda", "partition": "/dev/sda1"}
        for action in (
            self.service.resize_partition,
            self.service.format_partition,
            self.service.remove_pending,
            self.service.set_mountpoint,
            self.service.commit_partitions,
            self.service.rollback_partitions,
        ):
            with self.subTest(action=action.__name__):
                result = action(body)
                self.assertFalse(result["ok"])
                self.assertIn("No active partition journal", result["message"])

    def test_install_busy_and_cancel_outcomes(self):
        with patch(
            "kyth_installer.services.installer_service.validation.validate_install_request",
            return_value={},
        ), patch(
            "kyth_installer.services.installer_service.execution.start_installation",
            return_value=False,
        ):
            self.assertIn("already running", self.service.start_install({})["message"])

        with patch(
            "kyth_installer.services.installer_service.validation.validate_install_request",
            return_value={},
        ), patch(
            "kyth_installer.services.installer_service.execution.start_installation",
            return_value=True,
        ):
            self.assertTrue(self.service.start_install({})["started"])

        with patch(
            "kyth_installer.services.installer_service.execution.request_cancel",
            side_effect=[True, False],
        ):
            self.assertTrue(self.service.cancel_install({})["ok"])
            self.assertFalse(self.service.cancel_install({})["ok"])

    def test_preview_plan_reports_runtime_error_and_success(self):
        with patch(
            "kyth_installer.plan.validate_plan_state", side_effect=RuntimeError("unsafe disk")
        ):
            failed = self.service.preview_plan({})
        self.assertFalse(failed["valid"])
        self.assertEqual(failed["errors"], ("unsafe disk",))

        report = MagicMock(
            valid=True, mode="wipe", disk="/dev/sda", target_partition="/dev/sda1",
            efi_partition=None, will_create_partition=True,
            will_shrink_filesystem=False, needs_bios_boot=False,
            errors=(), warnings=("backup",),
        )
        with patch("kyth_installer.plan.validate_plan_state", return_value=report):
            success = self.service.preview_plan({})
        self.assertTrue(success["ok"])
        self.assertEqual(success["warnings"], ("backup",))

    # ── reboot ───────────────────────────────────────────────────────

    def test_reboot_success(self):
        with patch("kyth_installer.services.installer_service.runner.run_command") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            res = self.service.reboot({})
        self.assertTrue(res.get("ok"))

    def test_reboot_failure_reports_stderr(self):
        with patch("kyth_installer.services.installer_service.runner.run_command") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="reboot denied\n")
            res = self.service.reboot({})
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("error"), "reboot denied")


class AnswerFileTests(unittest.TestCase):
    def test_answer_file_rejects_symlink_wrong_owner_and_oversize(self):
        fd, path = tempfile.mkstemp()
        os.write(fd, b"{}")
        os.close(fd)
        try:
            real = os.lstat(path)
            for mode, uid, size, message in (
                (stat.S_IFLNK | 0o600, real.st_uid, 2, "regular file"),
                (real.st_mode, real.st_uid + 1, 2, "owned by"),
                (real.st_mode, real.st_uid, 65 * 1024, "too large"),
            ):
                fake = MagicMock(spec=real)
                fake.st_mode = mode
                fake.st_uid = uid
                fake.st_size = size
                with patch("kyth_installer.app.os.lstat", return_value=fake):
                    with self.assertRaisesRegex(ValueError, message):
                        _load_answer_file(path)
        finally:
            os.unlink(path)

    def test_answer_file_requires_json_object(self):
        fd, path = tempfile.mkstemp()
        try:
            os.write(fd, b"[]")
            os.close(fd)
            os.chmod(path, 0o600)
            with self.assertRaisesRegex(ValueError, "one JSON object"):
                _load_answer_file(path)
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
            os.unlink(path)

    def test_secure_answer_file_loads_supported_fields(self):
        fd, path = tempfile.mkstemp()
        try:
            os.write(fd, json.dumps({"disk": "/dev/sda", "password": "secret"}).encode())
            os.close(fd)
            os.chmod(path, 0o600)
            self.assertEqual(_load_answer_file(path)["disk"], "/dev/sda")
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
            os.unlink(path)

    def test_answer_file_rejects_permissions_that_expose_passwords(self):
        fd, path = tempfile.mkstemp()
        try:
            os.write(fd, b'{"password":"secret"}')
            os.close(fd)
            # Keep the test fixture itself secure, and simulate an insecure mode
            # at read time so validation still exercises the rejection path.
            os.chmod(path, 0o600)
            real_stat = os.lstat(path)
            fake_stat = MagicMock(spec=real_stat)
            fake_stat.st_mode = (real_stat.st_mode & ~0o777) | 0o644
            with patch("kyth_installer.app.os.lstat", return_value=fake_stat):
                with self.assertRaisesRegex(ValueError, "chmod 600"):
                    _load_answer_file(path)
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
            os.unlink(path)

    def test_answer_file_rejects_unknown_fields(self):
        fd, path = tempfile.mkstemp()
        try:
            os.write(fd, b'{"run_arbitrary_command":"bad"}')
            os.close(fd)
            os.chmod(path, 0o600)
            with self.assertRaisesRegex(ValueError, "Unknown installer answer-file fields"):
                _load_answer_file(path)
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
            os.unlink(path)

    @patch("sys.argv", ["/path/to/cmd", "--headless"])
    @patch("kyth_installer.services.installer_service.InstallerService")
    def test_headless_cli_entrypoint(self, mock_service_class):

        mock_service = MagicMock()
        mock_service.start_install.return_value = {"started": False, "message": "Failed to start"}
        mock_service_class.return_value = mock_service

        with patch("argparse.ArgumentParser.parse_known_args") as mock_parse:
            mock_args = MagicMock()
            mock_args.disk = "/dev/sda"
            mock_args.install_mode = "wipe"
            mock_args.username = "user"
            mock_args.password = "pass"
            mock_args.hostname = "kyth"
            mock_args.timezone = "UTC"
            mock_args.kernel = "fedora"
            mock_args.mok_password = ""
            mock_args.confirm_backup = True
            mock_args.confirm_erase = True
            mock_args.confirm_current = True
            mock_parse.return_value = (mock_args, [])
            
            with self.assertRaises(SystemExit) as cm:
                run_headless()
            self.assertEqual(cm.exception.code, 1)


class RunHeadlessEventLoopTests(unittest.TestCase):
    """run_headless()'s polling loop after a successful start_install() —
    covers the log/progress/error/done event types and the lifecycle-only
    fallback (no event) checked after the inner loop."""

    def _run_with_fake_service(self, populate):
        """`populate(context)` runs synchronously inside the mocked
        start_install(), before it returns {"started": True} — so the
        events/lifecycle it sets are already visible when run_headless()'s
        wait_for() predicate is first evaluated, and the loop never actually
        blocks on the 1s timeout."""
        def fake_service_ctor(context):
            service = MagicMock()

            def fake_start_install(_body):
                populate(context)
                return {"started": True}

            service.start_install.side_effect = fake_start_install
            return service

        argv = [
            "/path/to/cmd", "--headless", "--disk", "/dev/sda",
            "--username", "user", "--password", "pass",
        ]
        with patch("sys.argv", argv), \
             patch("kyth_installer.app.InstallerService", side_effect=fake_service_ctor):
            with self.assertRaises(SystemExit) as cm:
                run_headless()
        return cm.exception.code

    def test_prints_log_and_progress_then_exits_zero_on_done(self):
        def populate(context):
            context.events.publish({"type": "log", "text": "step 1"})
            context.events.publish({"type": "progress", "value": 42})
            context.events.publish({"type": "done", "mok_state": "enrolled"})

        self.assertEqual(self._run_with_fake_service(populate), 0)

    def test_error_event_exits_one(self):
        def populate(context):
            context.events.publish({"type": "error", "message": "disk write failed"})

        self.assertEqual(self._run_with_fake_service(populate), 1)

    def test_lifecycle_done_without_an_event_still_exits_zero(self):
        from kyth_installer.context import InstallLifecycle as _InstallLifecycle

        def populate(context):
            context.transition(_InstallLifecycle.VALIDATED)
            context.transition(_InstallLifecycle.INSTALLING)
            context.transition(_InstallLifecycle.DONE)

        self.assertEqual(self._run_with_fake_service(populate), 0)

    def test_lifecycle_failed_without_an_event_still_exits_one(self):
        from kyth_installer.context import InstallLifecycle as _InstallLifecycle

        def populate(context):
            context.transition(_InstallLifecycle.FAILED)

        self.assertEqual(self._run_with_fake_service(populate), 1)


if __name__ == "__main__":
    unittest.main()
