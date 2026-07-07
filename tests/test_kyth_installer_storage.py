import importlib.machinery
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_installer():
    loader = importlib.machinery.SourceFileLoader("kyth_installer_test", str(ROOT / "build_files/kyth-installer"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class InstallerStorageTests(unittest.TestCase):
    def setUp(self):
        self.installer = load_installer()

    def test_list_disks_excludes_protected_live_media(self):
        payload = {
            "blockdevices": [
                {"name": "/dev/nvme0n1", "size": 128 * 1024**3, "model": "Internal", "type": "disk", "tran": "nvme", "rota": False, "rm": False},
                {"name": "/dev/sdb", "size": 32 * 1024**3, "model": "Live USB", "type": "disk", "tran": "usb", "rota": False, "rm": True},
                {"name": "/dev/loop0", "size": 4 * 1024**3, "model": "Squashfs", "type": "disk", "tran": None, "rota": False, "rm": False},
            ]
        }

        with patch.object(self.installer, "_protected_install_disks", return_value={"/dev/sdb"}), \
             patch.object(self.installer.subprocess, "check_output", return_value=json.dumps(payload)):
            disks = self.installer.list_disks()

        self.assertEqual([d["name"] for d in disks], ["/dev/nvme0n1"])

    def test_list_partitions_marks_only_unmounted_btrfs_as_alongside_candidate(self):
        payload = {
            "blockdevices": [{
                "name": "/dev/nvme0n1",
                "type": "disk",
                "children": [
                    {"name": "/dev/nvme0n1p1", "size": 1024**3, "type": "part", "fstype": "vfat", "parttype": self.installer.EFI_PART_GUID, "label": "EFI", "mountpoints": ["/boot/efi"]},
                    {"name": "/dev/nvme0n1p2", "size": 80 * 1024**3, "type": "part", "fstype": "btrfs", "parttype": "", "label": "shared", "mountpoints": []},
                    {"name": "/dev/nvme0n1p3", "size": 40 * 1024**3, "type": "part", "fstype": "ext4", "parttype": "", "label": "other", "mountpoints": []},
                    {"name": "/dev/nvme0n1p4", "size": 40 * 1024**3, "type": "part", "fstype": "btrfs", "parttype": "", "label": "active", "mountpoints": ["/home"]},
                ],
            }]
        }

        with patch.object(self.installer.subprocess, "check_output", return_value=json.dumps(payload)):
            parts = {p["name"]: p for p in self.installer.list_partitions("/dev/nvme0n1")}

        self.assertFalse(parts["/dev/nvme0n1p1"]["alongside_candidate"])
        self.assertTrue(parts["/dev/nvme0n1p2"]["alongside_candidate"])
        self.assertFalse(parts["/dev/nvme0n1p3"]["alongside_candidate"])
        self.assertFalse(parts["/dev/nvme0n1p4"]["alongside_candidate"])

    def test_validate_alongside_requires_partition_on_selected_disk(self):
        with patch.object(self.installer, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.installer, "list_partitions", return_value=[]), \
             patch.object(self.installer, "_parent_disk", return_value="/dev/sda"):
            with self.assertRaisesRegex(RuntimeError, "does not belong"):
                self.installer._validate_install_target({
                    "install_mode": "alongside",
                    "disk": "/dev/nvme0n1",
                    "target_partition": "/dev/sda2",
                })

    def test_validate_alongside_requires_btrfs_partition(self):
        partition = {
            "name": "/dev/nvme0n1p2",
            "fstype": "ext4",
            "efi": False,
            "current": False,
        }
        with patch.object(self.installer, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.installer, "list_partitions", return_value=[partition]), \
             patch.object(self.installer, "_parent_disk", return_value="/dev/nvme0n1"):
            with self.assertRaisesRegex(RuntimeError, "Btrfs"):
                self.installer._validate_install_target({
                    "install_mode": "alongside",
                    "disk": "/dev/nvme0n1",
                    "target_partition": "/dev/nvme0n1p2",
                })

    def test_validate_wipe_rejects_disk_missing_from_safe_scan(self):
        with patch.object(self.installer, "list_disks", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "not a safe install target"):
                self.installer._validate_install_target({"install_mode": "wipe", "disk": "/dev/sda"})

    def test_validate_resize_ntfs_requires_last_partition(self):
        partition = {
            "name": "/dev/nvme0n1p3",
            "fstype": "ntfs",
            "efi": False,
            "current": False,
            "size_bytes": 256 * 1024**3,
        }
        with patch.object(self.installer, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.installer, "list_partitions", return_value=[partition]), \
             patch.object(self.installer, "_parent_disk", return_value="/dev/nvme0n1"), \
             patch.object(self.installer, "_partitions_after", return_value=[{"name": "/dev/nvme0n1p4"}]):
            with self.assertRaisesRegex(RuntimeError, "not the last partition"):
                self.installer._validate_resize_ntfs_target({
                    "disk": "/dev/nvme0n1",
                    "resize_partition": "/dev/nvme0n1p3",
                    "resize_gib": 64,
                })

    def test_validate_resize_ntfs_accepts_clean_last_ntfs_partition(self):
        partition = {
            "name": "/dev/nvme0n1p3",
            "fstype": "ntfs",
            "efi": False,
            "current": False,
            "size_bytes": 256 * 1024**3,
        }
        with patch.object(self.installer, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.installer, "list_partitions", return_value=[partition]), \
             patch.object(self.installer, "_parent_disk", return_value="/dev/nvme0n1"), \
             patch.object(self.installer, "_partitions_after", return_value=[]), \
             patch.object(self.installer, "find_efi_partition", return_value="/dev/nvme0n1p1"):
            disk, target, shrink = self.installer._validate_resize_ntfs_target({
                "disk": "/dev/nvme0n1",
                "resize_partition": "/dev/nvme0n1p3",
                "resize_gib": 64,
            })

        self.assertEqual(disk, "/dev/nvme0n1")
        self.assertEqual(target, "/dev/nvme0n1p3")
        self.assertEqual(shrink, 64 * 1024**3)

    def test_prepare_ntfs_resize_creates_btrfs_target_after_dry_run(self):
        partition = "/dev/nvme0n1p3"
        commands = []

        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            return self.installer.subprocess.CompletedProcess(cmd, 0, stdout="ok")

        with patch.object(self.installer.shutil, "which", return_value="/usr/bin/tool"), \
             patch.object(self.installer, "_validate_resize_ntfs_target", return_value=("/dev/nvme0n1", partition, 64 * 1024**3)), \
             patch.object(self.installer, "_partition_size_bytes", return_value=256 * 1024**3), \
             patch.object(self.installer, "_partition_number", return_value=3), \
             patch.object(self.installer, "_partition_start_bytes", return_value=128 * 1024**3), \
             patch.object(self.installer, "_block_size_bytes", return_value=512), \
             patch.object(self.installer, "list_partitions", side_effect=[
                 [{"name": "/dev/nvme0n1p1"}, {"name": partition}],
                 [{"name": "/dev/nvme0n1p1"}, {"name": partition}, {"name": "/dev/nvme0n1p4"}],
             ]), \
             patch.object(self.installer, "_settle_block_devices"), \
             patch.object(self.installer.subprocess, "run", side_effect=fake_run):
            created = self.installer._prepare_ntfs_resize_target(
                {"disk": "/dev/nvme0n1", "resize_partition": partition, "resize_gib": 64},
                lambda _msg: None,
            )

        self.assertEqual(created, ("/dev/nvme0n1", "/dev/nvme0n1p4"))
        flattened = [" ".join(cmd) for cmd in commands]
        self.assertTrue(any("ntfsresize --no-action" in cmd for cmd in flattened))
        self.assertTrue(any("parted -s /dev/nvme0n1 unit B resizepart 3" in cmd for cmd in flattened))
        self.assertTrue(any("mkfs.btrfs -f -L KythOS /dev/nvme0n1p4" in cmd for cmd in flattened))

    def test_find_efi_partition_reads_efi_key_without_keyerror(self):
        partitions = [
            {"name": "/dev/nvme0n1p1", "efi": False},
            {"name": "/dev/nvme0n1p2", "efi": True},
        ]
        with patch.object(self.installer, "list_partitions", return_value=partitions):
            result = self.installer.find_efi_partition("/dev/nvme0n1")

        self.assertEqual(result, "/dev/nvme0n1p2")

    def test_find_efi_partition_falls_back_to_findmnt_when_no_partition_flagged(self):
        with patch.object(self.installer, "list_partitions", return_value=[{"name": "/dev/nvme0n1p1", "efi": False}]), \
             patch.object(self.installer.subprocess, "check_output", return_value="/dev/nvme0n1p1\n"):
            result = self.installer.find_efi_partition("/dev/nvme0n1")

        self.assertEqual(result, "/dev/nvme0n1p1")

    def test_list_free_space_finds_trailing_gap_after_partitions(self):
        reserve = 1024**2
        p1_start = reserve
        p1_size = 1 * 1024**3 - reserve
        p2_start = p1_start + p1_size  # contiguous with p1, no gap between them
        p2_size = 39 * 1024**3
        disk_size = 120 * 1024**3

        partitions = [
            {"name": "/dev/nvme0n1p1", "size_bytes": p1_size},
            {"name": "/dev/nvme0n1p2", "size_bytes": p2_size},
        ]
        starts = {"/dev/nvme0n1p1": p1_start, "/dev/nvme0n1p2": p2_start}

        with patch.object(self.installer, "list_partitions", return_value=partitions), \
             patch.object(self.installer, "_partition_size_bytes", return_value=disk_size), \
             patch.object(self.installer, "_block_size_bytes", return_value=512), \
             patch.object(self.installer, "_partition_start_bytes", side_effect=lambda name: starts[name]):
            regions = self.installer.list_free_space("/dev/nvme0n1")

        self.assertEqual(len(regions), 1)
        region = regions[0]
        self.assertEqual(region["start_bytes"], p2_start + p2_size)
        self.assertEqual(region["end_bytes"], disk_size - reserve)
        self.assertGreater(region["end_bytes"] - region["start_bytes"], self.installer.MIN_KYTHOS_BYTES)

    def test_list_free_space_omits_gaps_smaller_than_minimum(self):
        partitions = [{"name": "/dev/nvme0n1p1", "size_bytes": 300 * 1024**2}]
        with patch.object(self.installer, "list_partitions", return_value=partitions), \
             patch.object(self.installer, "_partition_size_bytes", return_value=310 * 1024**2), \
             patch.object(self.installer, "_block_size_bytes", return_value=512), \
             patch.object(self.installer, "_partition_start_bytes", return_value=1024**2):
            regions = self.installer.list_free_space("/dev/nvme0n1")

        self.assertEqual(regions, [])

    def test_validate_free_space_rejects_region_below_minimum_size(self):
        with patch.object(self.installer, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.installer, "find_efi_partition", return_value="/dev/nvme0n1p1"):
            with self.assertRaisesRegex(RuntimeError, "at least"):
                self.installer._validate_free_space_target({
                    "disk": "/dev/nvme0n1",
                    "free_region_start": 1024**2,
                    "free_region_end": 16 * 1024**3,
                })

    def test_validate_free_space_rejects_stale_region_no_longer_free(self):
        with patch.object(self.installer, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.installer, "find_efi_partition", return_value="/dev/nvme0n1p1"), \
             patch.object(self.installer, "list_free_space", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "no longer available"):
                self.installer._validate_free_space_target({
                    "disk": "/dev/nvme0n1",
                    "free_region_start": 40 * 1024**3,
                    "free_region_end": 80 * 1024**3,
                })

    def test_validate_free_space_requires_efi_partition(self):
        with patch.object(self.installer, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.installer, "find_efi_partition", return_value=""):
            with self.assertRaisesRegex(RuntimeError, "EFI system partition"):
                self.installer._validate_free_space_target({
                    "disk": "/dev/nvme0n1",
                    "free_region_start": 40 * 1024**3,
                    "free_region_end": 80 * 1024**3,
                })

    def test_validate_free_space_accepts_region_covered_by_current_scan(self):
        with patch.object(self.installer, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.installer, "find_efi_partition", return_value="/dev/nvme0n1p1"), \
             patch.object(self.installer, "list_free_space", return_value=[
                 {"start_bytes": 40 * 1024**3, "end_bytes": 100 * 1024**3},
             ]):
            disk, start, end = self.installer._validate_free_space_target({
                "disk": "/dev/nvme0n1",
                "free_region_start": 40 * 1024**3,
                "free_region_end": 80 * 1024**3,
            })

        self.assertEqual((disk, start, end), ("/dev/nvme0n1", 40 * 1024**3, 80 * 1024**3))

    def test_prepare_free_space_target_creates_btrfs_partition(self):
        commands = []

        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            return self.installer.subprocess.CompletedProcess(cmd, 0, stdout="ok")

        with patch.object(self.installer.shutil, "which", return_value="/usr/bin/tool"), \
             patch.object(self.installer, "_validate_free_space_target", return_value=("/dev/nvme0n1", 40 * 1024**3, 80 * 1024**3)), \
             patch.object(self.installer, "list_partitions", return_value=[{"name": "/dev/nvme0n1p1"}]), \
             patch.object(self.installer, "_latest_partition_on_disk", return_value="/dev/nvme0n1p2"), \
             patch.object(self.installer, "_settle_block_devices"), \
             patch.object(self.installer.subprocess, "run", side_effect=fake_run):
            created = self.installer._prepare_free_space_target(
                {"disk": "/dev/nvme0n1", "free_region_start": 40 * 1024**3, "free_region_end": 80 * 1024**3},
                lambda _msg: None,
            )

        self.assertEqual(created, ("/dev/nvme0n1", "/dev/nvme0n1p2"))
        flattened = [" ".join(cmd) for cmd in commands]
        self.assertTrue(any(
            f"parted -s /dev/nvme0n1 unit B mkpart KythOS btrfs {40 * 1024**3}B {80 * 1024**3}B" in cmd
            for cmd in flattened
        ))
        self.assertTrue(any("mkfs.btrfs -f -L KythOS /dev/nvme0n1p2" in cmd for cmd in flattened))

    def test_prepare_free_space_target_requires_partitioning_tools(self):
        with patch.object(self.installer.shutil, "which", return_value=None), \
             patch.object(self.installer, "_validate_free_space_target", return_value=("/dev/nvme0n1", 40 * 1024**3, 80 * 1024**3)):
            with self.assertRaisesRegex(RuntimeError, "Required partitioning tools"):
                self.installer._prepare_free_space_target(
                    {"disk": "/dev/nvme0n1", "free_region_start": 40 * 1024**3, "free_region_end": 80 * 1024**3},
                    lambda _msg: None,
                )


if __name__ == "__main__":
    unittest.main()
