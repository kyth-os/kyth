import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files/kyth-installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from kyth_installer.cleanup import clear_secrets_and_orphan_mount, unmount_configuration
from kyth_installer.context import InstallLifecycle, InstallRequest, InstallerContext
from kyth_installer.execution import start_installation
from kyth_installer.validation import (
    InstallRequestError,
    validate_install_request,
    validate_partition_install_request,
)


class ImmediateThread:
    def __init__(self, *, target, daemon):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.target()


class InstallerBoundaryTests(unittest.TestCase):
    @patch("kyth_installer.validation.plan._validate_storage_intent")
    @patch("kyth_installer.validation.system._hash_password", return_value="hashed")
    @patch("kyth_installer.validation.system.list_timezones", return_value=["UTC"])
    @patch("kyth_installer.validation.disk.list_disks")
    def test_validation_returns_normalized_state(
        self,
        list_disks,
        _list_timezones,
        _hash_password,
        _validate_storage,
    ):
        list_disks.return_value = [{"name": "/dev/sda", "current": False}]
        state = validate_install_request(
            {
                "disk": "/dev/sda",
                "username": "kyth",
                "password": "secret",
                "hostname": "kyth-host",
                "confirm_backup": True,
                "confirm_erase": True,
            },
            InstallerContext(),
        )
        self.assertEqual(state["install_mode"], "wipe")
        self.assertEqual(state["username"], "kyth")
        self.assertEqual(state["password_hash"], "hashed")
        self.assertIsInstance(state, InstallRequest)
        with self.assertRaises(FrozenInstanceError):
            state.disk = "/dev/sdb"
        _validate_storage.assert_called_once()

    @patch("kyth_installer.validation.disk.list_disks")
    def test_validation_rejects_unknown_disk(self, list_disks):
        list_disks.return_value = []
        with self.assertRaisesRegex(InstallRequestError, "Invalid disk"):
            validate_install_request({"disk": "/dev/sda"}, InstallerContext())

    def test_partition_request_rejects_invalid_device_relationships(self):
        context = InstallerContext()
        with patch("kyth_installer.validation.disk._normal_device_path", return_value=None):
            with self.assertRaisesRegex(InstallRequestError, "Invalid target"):
                validate_partition_install_request(
                    target_partition="bad", efi_partition="", hostname="kyth",
                    timezone="UTC", username="", password="", context=context,
                )

        with (
            patch("kyth_installer.validation.disk._normal_device_path", return_value="/dev/sda1"),
            patch("kyth_installer.validation.disk._parent_disk", return_value=None),
        ):
            with self.assertRaisesRegex(InstallRequestError, "parent disk"):
                validate_partition_install_request(
                    target_partition="/dev/sda1", efi_partition="", hostname="kyth",
                    timezone="UTC", username="", password="", context=context,
                )

        with (
            patch("kyth_installer.validation.disk._normal_device_path", return_value="/dev/sda1"),
            patch("kyth_installer.validation.disk._parent_disk", return_value="/dev/sda"),
        ):
            with self.assertRaisesRegex(InstallRequestError, "must be different"):
                validate_partition_install_request(
                    target_partition="/dev/sda1", efi_partition="/dev/sda1", hostname="kyth",
                    timezone="UTC", username="", password="", context=context,
                )

    def test_partition_request_rejects_non_efi_and_incomplete_admin(self):
        context = InstallerContext()
        normal = lambda value: value
        with (
            patch("kyth_installer.validation.disk._normal_device_path", side_effect=normal),
            patch("kyth_installer.validation.disk._parent_disk", return_value="/dev/sda"),
            patch(
                "kyth_installer.validation.disk.list_partitions",
                return_value=[{"name": "/dev/sda2", "efi": False}],
            ),
        ):
            with self.assertRaisesRegex(InstallRequestError, "not an EFI"):
                validate_partition_install_request(
                    target_partition="/dev/sda1", efi_partition="/dev/sda2", hostname="kyth",
                    timezone="UTC", username="", password="", context=context,
                )

        with (
            patch("kyth_installer.validation.disk._normal_device_path", side_effect=normal),
            patch("kyth_installer.validation.disk._parent_disk", return_value="/dev/sda"),
            patch("kyth_installer.validation._storage_state", return_value=({}, {})),
            patch("kyth_installer.validation.system.list_timezones", return_value=["UTC"]),
        ):
            with self.assertRaisesRegex(InstallRequestError, "both be supplied"):
                validate_partition_install_request(
                    target_partition="/dev/sda1", efi_partition="", hostname="kyth",
                    timezone="UTC", username="admin", password="", context=context,
                )

    @patch("kyth_installer.execution.threading.Thread", ImmediateThread)
    def test_executor_owns_lifecycle_and_releases_lock(self):
        context = InstallerContext()
        worker = MagicMock()
        state = {"disk": "/dev/sda", "install_mode": "wipe"}

        self.assertTrue(start_installation(context, state, worker))

        worker.assert_called_once_with(context)
        self.assertEqual(context.lifecycle, InstallLifecycle.INSTALLING)
        self.assertTrue(context.install_lock.acquire(blocking=False))
        context.install_lock.release()

    def test_executor_refuses_when_install_slot_is_busy(self):
        context = InstallerContext()
        context.install_lock.acquire()
        try:
            self.assertFalse(start_installation(context, {}, MagicMock()))
        finally:
            context.install_lock.release()

    @patch("kyth_installer.execution.threading.Thread", ImmediateThread)
    def test_failed_attempt_can_be_retried_with_a_new_transaction(self):
        context = InstallerContext()
        context.transition(InstallLifecycle.FAILED)
        previous_id = context.transaction_id

        self.assertTrue(start_installation(context, {}, MagicMock()))

        self.assertEqual(context.lifecycle, InstallLifecycle.INSTALLING)
        self.assertNotEqual(context.transaction_id, previous_id)

    def test_context_rejects_invalid_lifecycle_jump(self):
        context = InstallerContext()

        with self.assertRaisesRegex(RuntimeError, "idle -> done"):
            context.transition(InstallLifecycle.DONE)

    def test_cleanup_clears_secrets_and_unmounts_orphan(self):
        state = {"password_hash": "hash", "mok_password": "mok"}
        run = MagicMock()
        clear_secrets_and_orphan_mount(state, "/run/kyth-target", run=run)
        self.assertEqual(state["password_hash"], "")
        self.assertEqual(state["mok_password"], "")
        self.assertIn("umount", run.call_args.args[0])

    def test_configuration_cleanup_has_single_mount_owner(self):
        run = MagicMock()
        unmount_configuration("/var/tmp/kyth-install-root", "", run=run)
        self.assertEqual(run.call_count, 2)
        self.assertIn("sync", run.call_args_list[0].args[0])
        self.assertIn("/var/tmp/kyth-install-root", run.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
