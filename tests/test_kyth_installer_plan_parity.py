"""Shared Rust/Python parity cases for the pure installer plan boundary."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer.context import InstallRequest  # noqa: E402
from kyth_installer import disk  # noqa: E402
from kyth_installer.disk import _normal_device_path  # noqa: E402
from kyth_installer.plan_request import install_plan_from_state  # noqa: E402
from kyth_installer.plan_validate import (  # noqa: E402
    GuidedValidationDependencies,
    ValidationDependencies,
    _validate_install_target,
    validate_free_space_target,
    validate_resize_ntfs_target,
)
from kyth_installer.storage_snapshot import StorageSnapshot  # noqa: E402


FIXTURE = ROOT / "src" / "kyth-installer-web" / "src-tauri" / "testdata" / "installer_plan_cases.json"
MIN_BYTES = 32 * 1024**3


def _cases() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _snapshot() -> StorageSnapshot:
    return StorageSnapshot(
        disks=({"name": "/dev/sda", "size_bytes": 200 * 1024**3},),
        partitions=({
            "name": "/dev/sda2",
            "fstype": "ntfs",
            "size_bytes": 200 * 1024**3,
        },),
        free_regions=({"start_bytes": 10, "end_bytes": 5},),
        efi_partition="/dev/sda1",
        is_gpt=False,
    )


class InstallerPlanParityTests(unittest.TestCase):
    def test_python_projection_matches_shared_valid_cases(self):
        for case in _cases():
            if "expected" not in case:
                continue
            with self.subTest(case=case["name"]):
                request = InstallRequest.from_state(case["input"])
                raw = case["input"]
                plan = install_plan_from_state(request)
                expected = case["expected"]
                self.assertEqual(plan.mode, expected["mode"])
                self.assertEqual(plan.disk, expected["disk"])
                self.assertEqual(
                    plan.target_partition or None,
                    _normal_device_path(case["input"].get("target_partition")),
                )
                # The Python projection intentionally remains storage-only,
                # but it must preserve every mode selector that the native
                # plan boundary consumes.  Resize/free-space values are
                # checked directly from the immutable request so this test
                # cannot accidentally bless a dropped field.
                if expected["mode"] == "resize_ntfs":
                    self.assertEqual(
                        _normal_device_path(
                            raw.get("resize_partition") or raw.get("target_partition")
                        ),
                        expected["resize_partition"],
                    )
                    self.assertEqual(
                        raw.get("resize_gib", 0) * 1024**3,
                        expected["resize_bytes"],
                    )
                else:
                    self.assertEqual(expected["resize_bytes"], 0)
                if expected["mode"] == "free_space":
                    self.assertEqual(raw.get("free_region_start", 0), expected["free_region_start"])
                    self.assertEqual(raw.get("free_region_end", 0), expected["free_region_end"])
                else:
                    self.assertIsNone(expected["free_region_start"])
                    self.assertIsNone(expected["free_region_end"])

    def test_python_validation_matches_shared_error_cases(self):
        snapshot = _snapshot()
        guided = GuidedValidationDependencies(
            probe_storage=lambda *_args, **_kwargs: snapshot,
            parent_disk=lambda _partition: "/dev/sda",
            partition_size=lambda _partition: 200 * 1024**3,
        )
        validation = ValidationDependencies(
            parent_disk=lambda _partition: "/dev/sda",
            list_partitions=lambda _disk: [],
            probe_storage=lambda *_args, **_kwargs: snapshot,
            get_journal=lambda _context: SimpleNamespace(committed=True, root_partition="/dev/sda2"),
        )
        for case in _cases():
            if "error_contains" not in case:
                continue
            with self.subTest(case=case["name"]):
                config = case["input"]
                mode = config.get("install_mode", "wipe").strip().lower() or "wipe"
                if mode == "resize_ntfs":
                    validator = lambda: validate_resize_ntfs_target(config, snapshot=snapshot, dependencies=guided)
                elif mode == "free_space":
                    validator = lambda: validate_free_space_target(config, snapshot=snapshot, dependencies=guided)
                else:
                    validator = lambda: _validate_install_target(config, object(), snapshot=snapshot, dependencies=validation)
                with self.assertRaisesRegex(RuntimeError, case["error_contains"]):
                    validator()

    def test_python_disk_discovery_matches_shared_lsblk_fixture(self):
        snapshot = json.loads(
            (ROOT / "src" / "kyth-installer-web" / "src-tauri" / "testdata" / "lsblk_snapshot.json")
            .read_text(encoding="utf-8")
        )
        with mock.patch.object(disk, "_lsblk_blockdevices", return_value=snapshot["blockdevices"]):
            partitions = disk.list_partitions("/dev/sda")
        self.assertEqual(
            [
                {
                    key: partition[key]
                    for key in (
                        "name", "size_bytes", "start_bytes", "fstype", "label", "parttype",
                        "mountpoints", "efi", "current", "in_use", "read_only",
                        "alongside_candidate", "ntfs_resize_candidate",
                    )
                }
                for partition in partitions
            ],
            [
                {
                    "name": "/dev/sda1",
                    "size_bytes": 1073741824,
                    "start_bytes": 1048576,
                    "fstype": "vfat",
                    "label": "",
                    "parttype": "c12a7328-f81f-11d2-ba4b-00a0c93ec93b",
                    "mountpoints": ["/boot/efi"],
                    "efi": True,
                    "current": True,
                    "in_use": False,
                    "read_only": False,
                    "alongside_candidate": False,
                    "ntfs_resize_candidate": False,
                },
                {
                    "name": "/dev/sda2",
                    "size_bytes": 214748364800,
                    "start_bytes": 1074790400,
                    "fstype": "ntfs",
                    "label": "",
                    "parttype": "e7bbf7e4-2e3c-4a05-9c2f-8b7b4f2a0e8f",
                    "mountpoints": ["/mnt"],
                    "efi": False,
                    "current": True,
                    "in_use": True,
                    "read_only": False,
                    "alongside_candidate": False,
                    "ntfs_resize_candidate": False,
                },
            ],
        )

    def test_python_disk_filtering_matches_shared_lsblk_fixture(self):
        snapshot = json.loads(
            (ROOT / "src" / "kyth-installer-web" / "src-tauri" / "testdata" / "lsblk_snapshot.json")
            .read_text(encoding="utf-8")
        )
        with mock.patch.object(disk, "_lsblk_tree", return_value={}), \
             mock.patch.object(disk, "_running_system_disk", return_value="/dev/sda2"), \
             mock.patch.object(disk, "_protected_install_disks", return_value={"/dev/sdb"}), \
             mock.patch.object(disk, "_parent_disk", return_value="/dev/sda"), \
             mock.patch.object(disk, "_lsblk_blockdevices", return_value=snapshot["blockdevices"]):
            disks = disk.list_disks()
        self.assertEqual(
            disks,
            [{
                "name": "/dev/sda",
                "size_bytes": 214748364800,
                "model": "Example SSD",
                "ssd": True,
                "transport": "nvme",
                "removable": False,
                "partition_table": "gpt",
                "current": True,
                "size": mock.ANY,
            }],
        )


if __name__ == "__main__":
    unittest.main()
