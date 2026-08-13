from __future__ import annotations

import contextlib
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer.context import InstallerContext, InstallPhase  # noqa: E402
from kyth_installer.phases import storage  # noqa: E402


class StorageRoutingTests(unittest.TestCase):
    @mock.patch.object(storage, "_prepare_install_storage", return_value=("target", "root", "mount"))
    def test_resolved_plan_fields_are_forwarded(self, prepare):
        plan = SimpleNamespace(
            disk="/dev/sda",
            mode="manual",
            source_ref="source",
            target_ref="target",
            target_partition="/dev/sda3",
            efi_partition="/dev/sda1",
        )
        context = InstallerContext()
        result = storage._prepare_storage_for_plan(
            plan, mock.Mock(), mock.Mock(), "old-mount", context
        )
        self.assertEqual(result, ("target", "root", "mount"))
        prepare.assert_called_once_with(
            "/dev/sda",
            "manual",
            "source",
            "target",
            mock.ANY,
            mock.ANY,
            "old-mount",
            context,
            target_partition="/dev/sda3",
            efi_partition="/dev/sda1",
        )

    def test_manual_mode_routes_explicit_partitions(self):
        context = InstallerContext()
        with (
            mock.patch("kyth_installer.execution.check_cancelled") as cancelled,
            mock.patch.object(storage, "_assert_still_on_ac") as power,
            mock.patch.object(
                storage,
                "_prepare_partition_target_storage",
                return_value=("target", "root", "mount"),
            ) as partition,
        ):
            result = storage._prepare_install_storage(
                "/dev/sda",
                "manual",
                "source",
                "target",
                mock.Mock(),
                mock.Mock(),
                "",
                context,
                target_partition="/dev/sda3",
                efi_partition="/dev/sda1",
            )
        self.assertEqual(result, ("target", "root", "mount"))
        cancelled.assert_called_once_with(context)
        power.assert_called_once()
        self.assertIs(context.phase, InstallPhase.STORAGE)
        self.assertEqual(partition.call_args.args[:2], ("/dev/sda3", "/dev/sda1"))

    def test_manual_mode_falls_back_to_context_partitions(self):
        context = InstallerContext()
        context.state.update(target_partition="/dev/vda2", efi_partition="/dev/vda1")
        with (
            mock.patch("kyth_installer.execution.check_cancelled"),
            mock.patch.object(storage, "_assert_still_on_ac"),
            mock.patch.object(
                storage, "_prepare_partition_target_storage", return_value=("a", "b", "c")
            ) as partition,
        ):
            storage._prepare_install_storage(
                "/dev/vda", "alongside", "source", "target", mock.Mock(), mock.Mock(), "", context
            )
        self.assertEqual(partition.call_args.args[:2], ("/dev/vda2", "/dev/vda1"))

    def test_wipe_mode_routes_disk(self):
        context = InstallerContext()
        with (
            mock.patch("kyth_installer.execution.check_cancelled"),
            mock.patch.object(storage, "_assert_still_on_ac"),
            mock.patch.object(
                storage, "_prepare_wipe_disk_storage", return_value=("", "/dev/sda3", "")
            ) as wipe,
        ):
            result = storage._prepare_install_storage(
                "/dev/sda", "wipe", "source", "target", mock.Mock(), mock.Mock(), "", context
            )
        self.assertEqual(result, ("", "/dev/sda3", ""))
        wipe.assert_called_once()


class BtrfsPreparationTests(unittest.TestCase):
    def test_btrfs_subvolumes_are_created_and_mount_is_released(self):
        context = InstallerContext()
        with (
            mock.patch("kyth_installer.install.run_command") as run,
            mock.patch("kyth_installer.install._as_root", side_effect=lambda cmd: cmd),
            mock.patch("kyth_installer.install._require_no_symlink") as safe_path,
            mock.patch("kyth_installer.install._safe_umount") as unmount,
            mock.patch("kyth_installer.install._run_cmd") as stream,
        ):
            storage._create_btrfs_subvolumes("/dev/sda3", mock.Mock(), mock.Mock(), context)

        stream.assert_called_once()
        safe_path.assert_called_once()
        self.assertTrue(any("subvolume" in " ".join(call.args[0]) for call in run.call_args_list))
        unmount.assert_called()
        self.assertEqual(context.mount_registry.snapshot(), [])

    def test_btrfs_failure_still_unmounts_and_releases(self):
        context = InstallerContext()

        def command(argv, **_kwargs):
            if "subvolume" in argv and "create" in argv:
                raise RuntimeError("create failed")
            return SimpleNamespace(returncode=0, stdout="")

        with (
            mock.patch("kyth_installer.install.run_command", side_effect=command),
            mock.patch("kyth_installer.install._as_root", side_effect=lambda cmd: cmd),
            mock.patch("kyth_installer.install._require_no_symlink"),
            mock.patch("kyth_installer.install._safe_umount") as unmount,
            mock.patch("kyth_installer.install._run_cmd"),
        ):
            with self.assertRaisesRegex(RuntimeError, "create failed"):
                storage._create_btrfs_subvolumes("/dev/sda3", mock.Mock(), mock.Mock(), context)
        self.assertGreaterEqual(unmount.call_count, 2)
        self.assertEqual(context.mount_registry.snapshot(), [])


class EfiHandlingTests(unittest.TestCase):
    def _mount_patches(self, findmnt_result):
        return (
            mock.patch("kyth_installer.install.run_command", side_effect=findmnt_result),
            mock.patch("kyth_installer.install._as_root", side_effect=lambda cmd: cmd),
        )

    def test_existing_efi_mount_is_bind_mounted(self):
        calls = []

        def run(argv, **_kwargs):
            calls.append(argv)
            if argv[0] == "findmnt":
                return SimpleNamespace(stdout="/boot/efi\n", returncode=0)
            return SimpleNamespace(stdout="", returncode=0)

        context = InstallerContext()
        log = mock.Mock()
        with (
            mock.patch("kyth_installer.install.run_command", side_effect=run),
            mock.patch("kyth_installer.install._as_root", side_effect=lambda cmd: cmd),
        ):
            storage._mount_efi_for_alongside("/target", "/dev/sda1", log, context)
        self.assertIn(["mount", "--bind", "/boot/efi", "/target/boot/efi"], calls)
        self.assertEqual(context.mount_registry.snapshot(), ["/target/boot/efi"])
        self.assertIn("bind-mounted", log.call_args.args[0])

    def test_unmounted_efi_partition_is_mounted_directly(self):
        calls = []

        def run(argv, **_kwargs):
            calls.append(argv)
            if argv[0] == "findmnt":
                raise RuntimeError("not mounted")
            return SimpleNamespace(stdout="", returncode=0)

        context = InstallerContext()
        log = mock.Mock()
        with (
            mock.patch("kyth_installer.install.run_command", side_effect=run),
            mock.patch("kyth_installer.install._as_root", side_effect=lambda cmd: cmd),
        ):
            storage._mount_efi_for_alongside("/target", "/dev/sda1", log, context)
        self.assertIn(["mount", "/dev/sda1", "/target/boot/efi"], calls)
        self.assertIn("mounted from /dev/sda1", log.call_args.args[0])

    @mock.patch("kyth_installer.phases.storage.shutil.which", return_value=None)
    def test_efi_snapshot_returns_empty_when_tool_is_missing(self, _which):
        self.assertEqual(storage._snapshot_efi_boot_entries(mock.Mock()), "")

    @mock.patch("kyth_installer.phases.storage.shutil.which", return_value="/usr/bin/efibootmgr")
    def test_efi_snapshot_handles_success_failure_and_exception(self, _which):
        cases = (
            (SimpleNamespace(returncode=0, stdout="Boot0001 Windows\n"), "Boot0001 Windows\n"),
            (SimpleNamespace(returncode=1, stdout="failed"), ""),
            (OSError("no efivars"), ""),
        )
        for outcome, expected in cases:
            with self.subTest(outcome=outcome), mock.patch(
                "kyth_installer.install.run_command",
                side_effect=outcome if isinstance(outcome, Exception) else None,
                return_value=None if isinstance(outcome, Exception) else outcome,
            ), mock.patch("kyth_installer.install._as_root", side_effect=lambda cmd: cmd):
                self.assertEqual(storage._snapshot_efi_boot_entries(mock.Mock()), expected)

    def test_disappeared_efi_entries_are_reported_sorted(self):
        before = "Boot0002* Windows Boot Manager\nBoot0003 Linux Rescue\nBootOrder: 0002,0003\n"
        after = "Boot0004* KythOS\n"
        log = mock.Mock()
        storage._warn_if_efi_boot_entries_disappeared(before, after, log)
        warning = log.call_args.args[0]
        self.assertIn("Linux Rescue, Windows Boot Manager", warning)

    def test_unchanged_or_missing_efi_snapshot_does_not_warn(self):
        log = mock.Mock()
        storage._warn_if_efi_boot_entries_disappeared("", "Boot0001 KythOS", log)
        storage._warn_if_efi_boot_entries_disappeared("Boot0001 KythOS", "Boot0001 KythOS", log)
        log.assert_not_called()


class WipeStorageTests(unittest.TestCase):
    def test_wipe_builds_command_runs_under_lock_and_returns_root(self):
        context = InstallerContext()
        context.cancel_requested = mock.Mock()
        command = ["bootc", "install", "to-disk"]
        with (
            mock.patch("kyth_installer.install.unmount_target_disk") as unmount,
            mock.patch("kyth_installer.install._build_bootc_install_cmd", return_value=command) as build,
            mock.patch("kyth_installer.install.get_root_partition", return_value="/dev/sda3"),
            mock.patch.object(storage, "_disk_image_hold", return_value=contextlib.nullcontext()),
            mock.patch("kyth_installer.install._run_cmd") as run,
        ):
            result = storage._prepare_wipe_disk_storage(
                "/dev/sda", "source", "target", mock.Mock(), mock.Mock(), "", context
            )
        self.assertEqual(result, ("", "/dev/sda3", ""))
        unmount.assert_called_once()
        build.assert_called_once_with(
            "to-disk", "source", "target", "/dev/sda", extra_flags=["--filesystem", "btrfs", "--wipe"]
        )
        run.assert_called_once()
        self.assertIs(context.phase, InstallPhase.IMAGE)


if __name__ == "__main__":
    unittest.main()
