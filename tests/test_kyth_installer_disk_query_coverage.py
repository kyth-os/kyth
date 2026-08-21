import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

import kyth_installer.disk as disk  # noqa: E402
from kyth_installer.disk import _query  # noqa: E402


class InstallerDiskQueryCoverageTests(unittest.TestCase):
    def test_mountpoint_helpers_accept_modern_legacy_and_nested_shapes(self):
        self.assertEqual(_query._partition_mountpoints({"mountpoints": [None, "/", "/home"]}), ["/", "/home"])
        self.assertEqual(_query._partition_mountpoints({"mountpoint": "/boot"}), ["/boot"])
        self.assertEqual(_query._partition_mountpoints({}), [])
        device = {"children": [{
            "mountpoint": "/outer",
            "children": [{"mountpoints": ["/inner"]}],
        }]}
        self.assertEqual(_query._descendant_mountpoints(device), ["/outer", "/inner"])
        self.assertTrue(_query._is_active_mount(["/"]))
        self.assertFalse(_query._is_active_mount([]))

    def test_list_disks_filters_invalid_entries_and_survives_scan_failure(self):
        devices = [
            {"name": "/dev/sr0", "type": "rom", "size": 1},
            {"name": "", "type": "disk", "size": 100},
            {"name": "/dev/loop0", "type": "disk", "size": 100},
            {"name": "/dev/sda", "type": "disk", "size": 0},
            {"name": "/dev/sdb", "type": "disk", "size": 100, "ro": True},
            {"name": "/dev/sdc", "type": "disk", "size": 100},
        ]
        common = [
            mock.patch.object(disk, "_lsblk_tree", return_value={}),
            mock.patch.object(disk, "_running_system_disk", return_value=""),
            mock.patch.object(disk, "_protected_install_disks", return_value={"/dev/sdc"}),
            mock.patch.object(disk, "_parent_disk", return_value=None),
        ]
        with common[0], common[1], common[2], common[3], mock.patch.object(
            disk, "_lsblk_blockdevices", return_value=devices
        ):
            self.assertEqual(_query.list_disks(), [])
        with mock.patch.object(disk, "_lsblk_tree", return_value={}), mock.patch.object(
            disk, "_running_system_disk", return_value=""
        ), mock.patch.object(disk, "_protected_install_disks", return_value=set()), mock.patch.object(
            disk, "_parent_disk", return_value=None
        ), mock.patch.object(disk, "_lsblk_blockdevices", side_effect=OSError("probe")):
            self.assertEqual(_query.list_disks(), [])

    def test_partition_scan_recurses_and_marks_ntfs_resize_candidate(self):
        large = (64 * 1024**3) + disk.MIN_KYTHOS_BYTES
        devices = [{"type": "disk", "children": [{
            "name": "/dev/sda2", "type": "part", "size": large,
            "start": 2048, "fstype": "NTFS3", "mountpoints": [],
        }]}]
        with mock.patch.object(disk, "_lsblk_blockdevices", return_value=devices):
            part = _query.list_partitions("/dev/sda")[0]
        self.assertTrue(part["alongside_candidate"])
        self.assertTrue(part["ntfs_resize_candidate"])
        self.assertEqual(part["start_bytes"], 2048 * 512)

    def test_partition_scan_invalid_path_and_strict_failure_policies(self):
        with mock.patch.object(disk, "_normal_device_path", return_value=None):
            self.assertEqual(_query.list_partitions("bad"), [])
        with mock.patch.object(disk, "_lsblk_blockdevices", side_effect=OSError("probe")):
            self.assertEqual(_query.list_partitions("/dev/sda"), [])
            with self.assertRaisesRegex(RuntimeError, "No storage changes were made"):
                _query.list_partitions("/dev/sda", strict=True)

    def test_free_space_fails_closed_for_bad_disk_and_partition_geometry(self):
        with mock.patch.object(disk, "_normal_device_path", return_value=None):
            self.assertEqual(_query.list_free_space("bad"), [])
        with mock.patch.object(disk, "_partition_size_bytes", side_effect=OSError):
            self.assertEqual(_query.list_free_space("/dev/sda"), [])

        invalid_parts = [
            [{"name": "", "size_bytes": 1024}],
            [{"name": "/dev/sda1", "size_bytes": 0}],
            [{"name": "/dev/sda1", "size_bytes": 4096, "start_bytes": -1}],
            [{"name": "/dev/sda1", "size_bytes": 8192, "start_bytes": 999999}],
        ]
        for parts in invalid_parts:
            with self.subTest(parts=parts), mock.patch.object(disk, "_partition_size_bytes", return_value=16384), mock.patch.object(
                disk, "_block_size_bytes", return_value=512
            ), mock.patch.object(disk, "list_partitions", return_value=parts), mock.patch.object(
                disk, "_partition_start_bytes", side_effect=OSError
            ):
                self.assertEqual(_query.list_free_space("/dev/sda"), [])

    def test_partition_scalar_helpers_validate_command_output(self):
        with mock.patch.object(disk, "_lsblk_text", return_value="3\n"):
            self.assertEqual(_query._partition_number("/dev/sda3"), 3)
        with mock.patch.object(disk, "_lsblk_text", return_value=""):
            with self.assertRaisesRegex(RuntimeError, "partition number"):
                _query._partition_number("/dev/sda3")
            with self.assertRaisesRegex(RuntimeError, "partition size"):
                _query._partition_size_bytes("/dev/sda3")
        with mock.patch.object(disk, "_lsblk_text", return_value="-1\n"):
            with self.assertRaisesRegex(RuntimeError, "partition start"):
                _query._partition_start_bytes("/dev/sda3")

    def test_partitions_after_walks_nested_tree_and_wraps_probe_failure(self):
        devices = [{"type": "disk", "children": [
            {"name": "/dev/sda1", "type": "part", "start": 2048},
            {"name": "/dev/sda2", "type": "part", "start": 4096},
            {"name": "/dev/mapper/x", "type": "crypt", "children": []},
        ]}]
        with mock.patch.object(disk, "_partition_start_bytes", return_value=2048 * 512), mock.patch.object(
            disk, "_lsblk_blockdevices", return_value=devices
        ):
            self.assertEqual([p["name"] for p in _query._partitions_after("/dev/sda", "/dev/sda1")], ["/dev/sda2"])
        with mock.patch.object(disk, "_partition_start_bytes", return_value=0), mock.patch.object(
            disk, "_lsblk_blockdevices", side_effect=OSError
        ):
            with self.assertRaisesRegex(RuntimeError, "partition order"):
                _query._partitions_after("/dev/sda", "/dev/sda1")

    def test_latest_partition_none_and_filesystem_contract(self):
        with mock.patch.object(disk, "list_partitions", return_value=[{"name": "/dev/sda1"}]):
            self.assertIsNone(_query._latest_partition_on_disk("/dev/sda", {"/dev/sda1"}))
        filesystems = {item["id"]: item for item in _query.list_filesystems()}
        self.assertTrue(filesystems["btrfs"]["root_ok"])
        self.assertTrue(filesystems["fat32"]["efi_ok"])

    def test_latest_partition_matches_geometry_not_highest_number(self):
        existing = [
            {"name": "/dev/sda1", "start_bytes": 1024**2, "size_bytes": 100 * 1024**3},
            {"name": "/dev/sda2", "start_bytes": 200 * 1024**3, "size_bytes": 50 * 1024**3},
        ]
        after = existing + [
            {"name": "/dev/sda3", "start_bytes": 300 * 1024**3, "size_bytes": 80 * 1024**3},
        ]
        with mock.patch.object(disk, "list_partitions", return_value=after):
            created = _query._latest_partition_on_disk(
                "/dev/sda",
                set(),  # empty before — previously would pick sda3 by max number
                start_bytes=200 * 1024**3,
                size_bytes=50 * 1024**3,
            )
        self.assertEqual(created, "/dev/sda2")

    def test_latest_partition_empty_before_without_geometry_fails_closed(self):
        parts = [
            {"name": "/dev/sda1", "start_bytes": 1024**2, "size_bytes": 100 * 1024**3},
            {"name": "/dev/sda2", "start_bytes": 200 * 1024**3, "size_bytes": 50 * 1024**3},
        ]
        with mock.patch.object(disk, "list_partitions", return_value=parts):
            self.assertIsNone(_query._latest_partition_on_disk("/dev/sda", set()))

    def test_latest_partition_unique_set_diff_without_geometry(self):
        after = [
            {"name": "/dev/sda1", "start_bytes": 1024**2, "size_bytes": 10 * 1024**3},
            {"name": "/dev/sda2", "start_bytes": 20 * 1024**3, "size_bytes": 40 * 1024**3},
        ]
        with mock.patch.object(disk, "list_partitions", return_value=after):
            self.assertEqual(
                _query._latest_partition_on_disk("/dev/sda", {"/dev/sda1"}),
                "/dev/sda2",
            )


if __name__ == "__main__":
    unittest.main()
