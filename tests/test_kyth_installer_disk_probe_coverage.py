import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

import kyth_installer.disk as disk  # noqa: E402
from kyth_installer.disk import _probe  # noqa: E402


class InstallerDiskProbeCoverageTests(unittest.TestCase):
    def test_running_system_disk_returns_mount_source_or_empty_on_failure(self):
        with mock.patch.object(disk, "_findmnt_source", return_value="/dev/mapper/root"):
            self.assertEqual(_probe._running_system_disk(), "/dev/mapper/root")
        with mock.patch.object(disk, "_findmnt_source", side_effect=OSError):
            self.assertEqual(_probe._running_system_disk(), "")

    def test_live_usb_resolves_parent_name_direct_disk_and_child_disk(self):
        cases = [
            ({"name": "sdb1", "pkname": "sdb", "type": "part"}, "/dev/sdb"),
            ({"name": "/dev/sdc", "type": "disk"}, "/dev/sdc"),
            ({"name": "holder", "type": "part", "children": [{"name": "sdd", "type": "disk"}]}, "/dev/sdd"),
        ]
        for device, expected in cases:
            with self.subTest(device=device), mock.patch.object(
                disk, "_findmnt_source", return_value="/dev/source"
            ), mock.patch.object(
                disk, "run_command", return_value=SimpleNamespace(stdout=json.dumps({"blockdevices": [device]}))
            ):
                self.assertEqual(_probe._get_live_usb_disk(), expected)

    def test_live_usb_tries_iso_after_empty_live_mount_and_handles_bad_json(self):
        with mock.patch.object(disk, "_findmnt_source", side_effect=["", "/dev/sr0"]), mock.patch.object(
            disk, "run_command", return_value=SimpleNamespace(stdout="not-json")
        ):
            self.assertIsNone(_probe._get_live_usb_disk())

    def test_parent_disk_handles_unknown_devices_missing_parents_and_cycles(self):
        with mock.patch.object(disk, "_normal_device_path", side_effect=lambda value: value), mock.patch.object(
            disk, "_device_type", return_value="part"
        ), mock.patch.object(disk, "_lsblk_text", return_value=""):
            self.assertIsNone(_probe._parent_disk("/dev/missing", tree={}))

        no_parent = {"/dev/sda1": {"type": "part", "pkname": None}}
        self.assertIsNone(_probe._parent_disk("/dev/sda1", tree=no_parent))
        cycle = {
            "/dev/a": {"type": "crypt", "pkname": "/dev/b"},
            "/dev/b": {"type": "lvm", "pkname": "/dev/a"},
        }
        self.assertIsNone(_probe._parent_disk("/dev/a", tree=cycle))

    def test_mount_sources_normalizes_devices_and_ignores_non_devices(self):
        output = "/dev/sda1\n/dev/disk/by-label/ROOT\noverlay\n"
        with mock.patch.object(disk, "run_command", return_value=SimpleNamespace(stdout=output)), mock.patch(
            "kyth_installer.disk._probe.os.path.realpath", side_effect=lambda value: value.replace("by-label/ROOT", "sda2")
        ):
            self.assertEqual(_probe._mount_sources("/", recursive=True), {"/dev/sda1", "/dev/disk/sda2"})
            self.assertIn("-R", disk.run_command.call_args.args[0])
        with mock.patch.object(disk, "run_command", side_effect=OSError):
            self.assertEqual(_probe._mount_sources("/"), set())

    def test_protected_disks_collect_running_fixed_and_recursive_mounts(self):
        sources = {
            "/": {"/dev/root"},
            "/boot": {"/dev/boot"},
            "/run/initramfs": {"/dev/live"},
            "/run/media": {"/dev/media"},
        }
        with mock.patch.object(disk, "_lsblk_tree", return_value={"snapshot": {}}) as tree, mock.patch.object(
            disk, "_running_system_disk", return_value="/dev/running"
        ), mock.patch.object(
            disk, "_mount_sources", side_effect=lambda path, recursive=False: sources.get(path, set())
        ), mock.patch.object(
            disk, "_parent_disk", side_effect=lambda dev, tree=None: dev.replace("/dev/", "/dev/disk-") if dev else None
        ), mock.patch.object(_probe, "_IS_LIVE_SESSION", True):
            protected = _probe._protected_install_disks()
        self.assertEqual(
            protected,
            {"/dev/disk-running", "/dev/disk-root", "/dev/disk-boot", "/dev/disk-live", "/dev/disk-media"},
        )
        tree.assert_called_once()

    def test_non_live_session_does_not_protect_removable_media_mounts(self):
        with mock.patch.object(disk, "_mount_sources", side_effect=lambda path, recursive=False: {"/dev/media"} if path == "/run/media" else set()), mock.patch.object(
            disk, "_parent_disk", side_effect=lambda dev, tree=None: "/dev/sdb" if dev else None
        ) as parent, mock.patch.object(_probe, "_IS_LIVE_SESSION", False):
            protected = _probe._protected_install_disks(tree={}, running_disk="")
        self.assertEqual(protected, set())
        self.assertEqual(parent.call_count, 1)

    def test_disk_path_and_active_mount_checks_fail_safe(self):
        for path in ("/dev/loop0", "/dev/ram0", "/dev/zram0", "sda"):
            self.assertFalse(_probe._disk_path_is_safe(path))
        self.assertTrue(_probe._disk_path_is_safe("/dev/nvme0n1"))
        with mock.patch.object(disk, "run_command", return_value=SimpleNamespace(stdout="/mnt\n")):
            self.assertTrue(_probe.partition_has_active_mount("/dev/sda1"))
        with mock.patch.object(disk, "run_command", return_value=SimpleNamespace(stdout="")):
            self.assertFalse(_probe.partition_has_active_mount("/dev/sda1"))
        with mock.patch.object(disk, "run_command", side_effect=OSError):
            self.assertFalse(_probe.partition_has_active_mount("/dev/sda1"))


if __name__ == "__main__":
    unittest.main()
