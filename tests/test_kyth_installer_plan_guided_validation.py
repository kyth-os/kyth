import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer.config import MIN_KYTHOS_BYTES  # noqa: E402
from kyth_installer.plan_validate import (  # noqa: E402
    GuidedValidationDependencies,
    ReportDependencies,
    build_plan_report,
    validate_free_space_target,
    validate_resize_ntfs_target,
)
from kyth_installer.storage_snapshot import StorageSnapshot  # noqa: E402
from kyth_installer.context import InstallRequest  # noqa: E402


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

    def report_dependencies(self, **changes):
        values = {
            "as_request": lambda state: (
                state if isinstance(state, InstallRequest) else InstallRequest.from_state(state)
            ),
            "normalized_mode": lambda request: request.install_mode,
            "probe_storage": lambda *_args, **_kwargs: self.snapshot(),
            "validate_install": lambda *_args, **_kwargs: ("/dev/sda", None),
            "validate_resize": lambda *_args, **_kwargs: (
                "/dev/sda", "/dev/sda2", 40 * 1024**3,
            ),
            "validate_free_space": lambda *_args, **_kwargs: (
                "/dev/sda", 1024**2, 40 * 1024**3 + 1024**2,
            ),
        }
        values.update(changes)
        return ReportDependencies(**values)

    def test_report_builder_covers_wipe_and_runtime_validation_error(self):
        snapshot = StorageSnapshot(
            disks=({"name": "/dev/sda", "size_bytes": 100 * 1024**3},),
            partitions=(), free_regions=(), efi_partition=None, is_gpt=False,
        )
        report = build_plan_report(
            {"disk": "/dev/sda", "install_mode": "wipe"}, snapshot=snapshot,
            dependencies=self.report_dependencies(),
        )
        self.assertTrue(report.valid)
        self.assertEqual(report.available_bytes, 100 * 1024**3)

        failed = build_plan_report(
            {"disk": "/dev/sda", "install_mode": "wipe"}, snapshot=snapshot,
            dependencies=self.report_dependencies(
                validate_install=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("unsafe target")
                )
            ),
        )
        self.assertFalse(failed.valid)
        self.assertEqual(failed.errors, ("unsafe target",))

    def test_report_builder_warns_for_guided_bios_creation(self):
        snapshot = StorageSnapshot(
            disks=({"name": "/dev/sda"},), partitions=(), free_regions=(),
            efi_partition="/dev/sda1", is_gpt=True,
        )
        report = build_plan_report(
            {"disk": "/dev/sda", "install_mode": "resize_ntfs"}, snapshot=snapshot,
            dependencies=self.report_dependencies(),
        )
        self.assertTrue(report.valid)
        self.assertTrue(report.needs_bios_boot)
        self.assertIn("BIOS boot partition", report.warnings[0])

    def test_report_builder_rejects_alongside_without_bios_helper(self):
        snapshot = StorageSnapshot(
            disks=({"name": "/dev/sda"},),
            partitions=({"name": "/dev/sda2", "size_bytes": 80 * 1024**3},),
            free_regions=(), efi_partition="/dev/sda1", is_gpt=True,
        )
        report = build_plan_report(
            {"disk": "/dev/sda", "install_mode": "alongside"}, snapshot=snapshot,
            dependencies=self.report_dependencies(
                validate_install=lambda *_args, **_kwargs: ("/dev/sda", "/dev/sda2")
            ),
        )
        self.assertFalse(report.valid)
        self.assertIn("Legacy BIOS", report.errors[0])

    def test_report_builder_translates_unexpected_dependency_error(self):
        report = build_plan_report(
            {"disk": "/dev/sda", "install_mode": "free_space"},
            dependencies=self.report_dependencies(
                validate_free_space=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    ValueError("broken probe")
                )
            ),
        )
        self.assertFalse(report.valid)
        self.assertIn("Unexpected validation error", report.errors[0])


if __name__ == "__main__":
    unittest.main()
