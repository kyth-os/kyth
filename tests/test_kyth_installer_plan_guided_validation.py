import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer.config import MIN_KYTHOS_BYTES  # noqa: E402
from kyth_installer.plan_validate import (  # noqa: E402
    GuidedValidationDependencies,
    validate_free_space_target,
    validate_resize_ntfs_target,
)
from kyth_installer.storage_snapshot import StorageSnapshot  # noqa: E402


class GuidedPlanValidationTests(unittest.TestCase):
    def dependencies(self):
        return GuidedValidationDependencies(
            probe_storage=lambda *_args, **_kwargs: None,
            parent_disk=lambda _partition: "/dev/sda",
            partition_size=lambda _partition: 200 * 1024**3,
        )

    def snapshot(self, *, filesystem="ntfs", efi="/dev/sda1", free=()):
        return StorageSnapshot(
            disks=({"name": "/dev/sda"},),
            partitions=({
                "name": "/dev/sda2", "fstype": filesystem,
                "size_bytes": 200 * 1024**3,
            },),
            free_regions=tuple(free), efi_partition=efi, is_gpt=False,
        )

    def test_ntfs_resize_returns_normalized_destructive_input(self):
        result = validate_resize_ntfs_target(
            {"disk": "/dev/sda", "resize_partition": "/dev/sda2", "resize_gib": 40},
            snapshot=self.snapshot(), dependencies=self.dependencies(),
        )
        self.assertEqual(result, ("/dev/sda", "/dev/sda2", 40 * 1024**3))

    def test_ntfs_resize_rejects_wrong_filesystem_and_missing_efi(self):
        config = {"disk": "/dev/sda", "resize_partition": "/dev/sda2", "resize_gib": 40}
        with self.assertRaisesRegex(RuntimeError, "Only NTFS"):
            validate_resize_ntfs_target(
                config, snapshot=self.snapshot(filesystem="ext4"),
                dependencies=self.dependencies(),
            )
        with self.assertRaisesRegex(RuntimeError, "EFI system partition"):
            validate_resize_ntfs_target(
                config, snapshot=self.snapshot(efi=None), dependencies=self.dependencies(),
            )

    def test_free_space_requires_exact_current_region(self):
        start = 1024**2
        end = start + MIN_KYTHOS_BYTES
        config = {"disk": "/dev/sda", "free_region_start": start, "free_region_end": end}
        snapshot = self.snapshot(free=({"start_bytes": start, "end_bytes": end},))
        self.assertEqual(
            validate_free_space_target(
                config, snapshot=snapshot, dependencies=self.dependencies(),
            ),
            ("/dev/sda", start, end),
        )
        with self.assertRaisesRegex(RuntimeError, "no longer available"):
            validate_free_space_target(
                config, snapshot=self.snapshot(), dependencies=self.dependencies(),
            )


if __name__ == "__main__":
    unittest.main()
