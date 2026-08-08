import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files" / "kyth-installer"
sys.path.insert(0, str(INSTALLER_ROOT))

from kyth_installer import partition_cli
from kyth_installer.context import InstallLifecycle, InstallerContext
from kyth_installer.validation import (
    InstallRequestError,
    validate_partition_install_request,
)


class PartitionInstallValidationTests(unittest.TestCase):
    @mock.patch("kyth_installer.validation.plan._validate_storage_intent")
    @mock.patch("kyth_installer.validation.system._hash_password", return_value="hashed")
    @mock.patch(
        "kyth_installer.validation.system.list_timezones",
        return_value=["UTC", "America/Detroit"],
    )
    @mock.patch(
        "kyth_installer.validation.disk.list_partitions",
        side_effect=[
            [{"name": "/dev/sda1", "efi": True}],
            [{"name": "/dev/sda2"}],
        ],
    )
    @mock.patch(
        "kyth_installer.validation.disk.list_disks",
        return_value=[{"name": "/dev/sda", "current": False}],
    )
    @mock.patch(
        "kyth_installer.validation.disk._parent_disk",
        return_value="/dev/sda",
    )
    @mock.patch(
        "kyth_installer.validation.disk._normal_device_path",
        side_effect=lambda path: path,
    )
    def test_request_uses_alongside_policy_and_allows_skipping_user(
        self,
        _normal_device,
        _parent_disk,
        _list_disks,
        _list_partitions,
        _timezones,
        hash_password,
        validate_storage,
    ):
        state = validate_partition_install_request(
            target_partition="/dev/sda2",
            efi_partition="/dev/sda1",
            hostname="kyth",
            timezone="UTC",
            username="",
            password="",
            context=InstallerContext(),
        )
        self.assertEqual(state["install_mode"], "alongside")
        self.assertEqual(state["disk"], "/dev/sda")
        self.assertEqual(state["target_partition"], "/dev/sda2")
        self.assertEqual(state["efi_partition"], "/dev/sda1")
        self.assertEqual(state["password_hash"], "")
        hash_password.assert_not_called()
        validate_storage.assert_called_once()

    @mock.patch("kyth_installer.validation.disk._parent_disk", return_value="/dev/sda")
    @mock.patch(
        "kyth_installer.validation.disk._normal_device_path",
        side_effect=lambda path: path,
    )
    @mock.patch(
        "kyth_installer.validation.disk.list_partitions",
        return_value=[{"name": "/dev/sda1", "efi": False}],
    )
    def test_rejects_non_efi_partition(
        self, _list_partitions, _normal_device, _parent_disk
    ):
        with self.assertRaisesRegex(InstallRequestError, "not an EFI"):
            validate_partition_install_request(
                target_partition="/dev/sda2",
                efi_partition="/dev/sda1",
                hostname="kyth",
                timezone="UTC",
                username="",
                password="",
                context=InstallerContext(),
            )

    @mock.patch(
        "kyth_installer.validation.disk._normal_device_path",
        side_effect=lambda path: path,
    )
    @mock.patch(
        "kyth_installer.validation.disk._parent_disk",
        return_value="/dev/sda",
    )
    def test_rejects_target_as_efi(self, _parent_disk, _normal_device):
        with self.assertRaisesRegex(InstallRequestError, "must be different"):
            validate_partition_install_request(
                target_partition="/dev/sda2",
                efi_partition="/dev/sda2",
                hostname="kyth",
                timezone="UTC",
                username="",
                password="",
                context=InstallerContext(),
            )


class PartitionInstallCliTests(unittest.TestCase):
    @mock.patch("kyth_installer.partition_cli.system.require_root")
    @mock.patch(
        "kyth_installer.partition_cli._describe_target",
        return_value=("/dev/sda2", "/dev/sda", "/dev/sda1"),
    )
    @mock.patch("kyth_installer.partition_cli._print_plan")
    def test_exact_confirmation_is_required(
        self, _print_plan, _describe_target, _require_root
    ):
        result = partition_cli.run(
            ["/dev/sda2"],
            input_fn=lambda _prompt: "no",
        )
        self.assertEqual(result, 0)

    @mock.patch("kyth_installer.partition_cli.system.require_root")
    @mock.patch(
        "kyth_installer.partition_cli._describe_target",
        return_value=("/dev/sda2", "/dev/sda", "/dev/sda1"),
    )
    @mock.patch("kyth_installer.partition_cli._print_plan")
    @mock.patch("kyth_installer.partition_cli.validate_partition_install_request")
    @mock.patch("kyth_installer.partition_cli.start_installation")
    @mock.patch("kyth_installer.partition_cli._render_events", return_value=0)
    def test_cli_starts_shared_installer_worker(
        self,
        render_events,
        start_installation,
        validate_request,
        _print_plan,
        _describe_target,
        _require_root,
    ):
        state = {"disk": "/dev/sda", "install_mode": "alongside"}
        validate_request.return_value = state
        start_installation.return_value = True
        answers = iter(["install kythos", "host", "UTC", ""])

        result = partition_cli.run(
            ["/dev/sda2", "/dev/sda1"],
            input_fn=lambda _prompt: next(answers),
        )

        self.assertEqual(result, 0)
        context = start_installation.call_args.args[0]
        self.assertIsInstance(context, InstallerContext)
        self.assertEqual(start_installation.call_args.args[1], state)
        self.assertIs(start_installation.call_args.args[2], partition_cli.install._run_install)
        render_events.assert_called_once_with(context)

    def test_event_renderer_returns_failure_and_surfaces_error(self):
        context = InstallerContext()
        context.transition(InstallLifecycle.FAILED)
        context.events.publish({"type": "error", "message": "boom"})
        with mock.patch("sys.stderr"):
            self.assertEqual(partition_cli._render_events(context), 1)


if __name__ == "__main__":
    unittest.main()
