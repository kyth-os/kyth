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


if __name__ == "__main__":
    unittest.main()
