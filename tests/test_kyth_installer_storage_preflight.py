"""Typed storage preflight parity: ESP preservation, Windows indicator, and
locked-BitLocker detection shared with the Rust installer preflight
(``installer_storage::storage_preflight_from_snapshot``) over the same
``list_partitions`` detection source."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer.disk import _query  # noqa: E402
from kyth_installer import plan_validate  # noqa: E402


def _parts():
    return [
        {"name": "/dev/sda1", "efi": True, "fstype": "vfat",
         "parttype": "c12a7328-f81f-11d2-ba4b-00a0c93ec93b",
         "label": "ESP", "in_use": False},
        {"name": "/dev/sda2", "efi": False, "fstype": "ntfs",
         "parttype": "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7",
         "label": "Windows", "in_use": False},
        {"name": "/dev/sda3", "efi": False, "fstype": "btrfs",
         "parttype": "", "label": "KythOS", "in_use": False},
    ]


class StoragePreflightTests(unittest.TestCase):
    def test_preflight_detects_esp_windows_and_clean_disk(self):
        report = _query.storage_preflight(_parts())
        self.assertTrue(report["esp_present"])
        self.assertEqual(report["esp_name"], "/dev/sda1")
        self.assertTrue(report["windows_present"])
        self.assertFalse(report["bitlocker_locked"])
        self.assertEqual(report["checked_partitions"], 3)
        plan_validate.validate_storage_preflight(report, "alongside")

    def test_preflight_flags_explicit_bitlocker_and_ntfs_with_mappings(self):
        locked = _parts()
        locked[1] = dict(locked[1], fstype="bitlocker")
        self.assertTrue(_query.storage_preflight(locked)["bitlocker_locked"])

        mapped = _parts()
        mapped[1] = dict(mapped[1], in_use=True)
        self.assertTrue(_query.storage_preflight(mapped)["bitlocker_locked"])

    def test_preflight_detects_windows_by_guid_or_label(self):
        guid_only = [{"name": "/dev/sda2", "fstype": "",
                      "parttype": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
                      "label": "", "efi": False}]
        self.assertTrue(_query.storage_preflight(guid_only)["windows_present"])
        label_only = [{"name": "/dev/sda2", "fstype": "ext4",
                       "parttype": "", "label": "Windows11", "efi": False}]
        self.assertTrue(_query.storage_preflight(label_only)["windows_present"])

    def test_validate_fails_closed_on_locked_bitlocker_in_every_mode(self):
        locked = dict(_query.storage_preflight(_parts()), bitlocker_locked=True)
        for mode in ("wipe", "alongside", "resize_ntfs", "free_space", "manual"):
            with self.subTest(mode=mode), self.assertRaisesRegex(RuntimeError, "BitLocker"):
                plan_validate.validate_storage_preflight(locked, mode)

    def test_validate_requires_esp_preservation_off_wipe(self):
        bare = _query.storage_preflight([
            {"name": "/dev/sda1", "efi": False, "fstype": "ext4",
             "parttype": "", "label": "", "in_use": False},
        ])
        self.assertFalse(bare["esp_present"])
        plan_validate.validate_storage_preflight(bare, "wipe")
        for mode in ("alongside", "resize_ntfs", "free_space", "manual"):
            with self.subTest(mode=mode), self.assertRaisesRegex(RuntimeError, "EFI system partition"):
                plan_validate.validate_storage_preflight(bare, mode)

    def test_check_storage_preflight_rejects_locked_disk_snapshot(self):
        from kyth_installer.storage_snapshot import StorageSnapshot

        snapshot = StorageSnapshot(
            disks=({"name": "/dev/sda"},),
            partitions=(
                {"name": "/dev/sda1", "efi": True, "fstype": "vfat"},
                {"name": "/dev/sda2", "fstype": "bitlocker"},
            ),
            free_regions=(), efi_partition="/dev/sda1", is_gpt=True,
        )
        with self.assertRaisesRegex(RuntimeError, "BitLocker"):
            plan_validate._check_storage_preflight(snapshot, "wipe")


if __name__ == "__main__":
    unittest.main()
