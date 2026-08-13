import sys
import unittest
from unittest import mock
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer.config import MIN_KYTHOS_BYTES  # noqa: E402
from kyth_installer.plan_validate import (  # noqa: E402
    GuidedValidationDependencies,
    ReportDependencies,
    ValidationDependencies,
    _validate_install_target,
    build_plan_report,
    validate_free_space_target,
    validate_resize_ntfs_target,
    validate_storage_intent,
)
from kyth_installer.storage_snapshot import StorageSnapshot  # noqa: E402
from kyth_installer.context import InstallRequest  # noqa: E402


class GuidedPlanValidationTests(unittest.TestCase):
    def test_storage_intent_dispatches_all_mode_families(self):
        validators = {
            "validate_install": mock.Mock(),
            "validate_resize": mock.Mock(),
            "validate_free_space": mock.Mock(),
        }
        for mode, expected in (
            ("resize_ntfs", "validate_resize"),
            ("free_space", "validate_free_space"),
            ("manual", "validate_install"),
            ("wipe", "validate_install"),
        ):
            for validator in validators.values():
                validator.reset_mock()
            validate_storage_intent(
                {"install_mode": mode}, object(), object(),
                normalized_mode=lambda state: state["install_mode"], **validators,
            )
            validators[expected].assert_called_once()

    def dependencies(self, **changes):
        values = {
            "probe_storage": lambda *_args, **_kwargs: None,
            "parent_disk": lambda _partition: "/dev/sda",
            "partition_size": lambda _partition: 200 * 1024**3,
        }
        values.update(changes)
        return GuidedValidationDependencies(**values)

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

    def test_ntfs_resize_rejects_drift_reserved_space_and_unsafe_remainder(self):
        config = {"disk": "/dev/sda", "resize_partition": "/dev/sda2", "resize_gib": 40}
        cases = (
            (self.dependencies(parent_disk=lambda _partition: "/dev/sdb"), self.snapshot(), "does not belong"),
            (self.dependencies(), StorageSnapshot(
                disks=({"name": "/dev/sda"},), partitions=(), free_regions=(),
                efi_partition="/dev/sda1", is_gpt=False,
            ), "not found"),
            (self.dependencies(), StorageSnapshot(
                disks=({"name": "/dev/sda"},), partitions=({
                    "name": "/dev/sda2", "fstype": "ntfs", "current": True,
                    "size_bytes": 200 * 1024**3,
                },), free_regions=(), efi_partition="/dev/sda1", is_gpt=False,
            ), "mounted"),
            (self.dependencies(), self.snapshot(), "smaller than 64"),
        )
        for dependencies, snapshot, message in cases:
            selected = dict(config)
            if message == "smaller than 64":
                selected["resize_gib"] = 140
            with self.subTest(message=message), self.assertRaisesRegex(RuntimeError, message):
                validate_resize_ntfs_target(
                    selected, snapshot=snapshot, dependencies=dependencies,
                )

        gpt = StorageSnapshot(
            disks=({"name": "/dev/sda"},), partitions=({
                "name": "/dev/sda2", "fstype": "ntfs", "size_bytes": 200 * 1024**3,
            },), free_regions=(), efi_partition="/dev/sda1", is_gpt=True,
        )
        with self.assertRaisesRegex(RuntimeError, "boot partition"):
            validate_resize_ntfs_target(
                {**config, "resize_gib": 32}, snapshot=gpt,
                dependencies=self.dependencies(),
            )

    def test_explicit_validation_rejects_partition_and_manual_invariants(self):
        snapshot = StorageSnapshot(
            disks=({"name": "/dev/sda", "size_bytes": 100 * 1024**3},),
            partitions=({"name": "/dev/sda2", "size_bytes": 80 * 1024**3},),
            free_regions=(), efi_partition="/dev/sda1", is_gpt=False,
        )
        journal = SimpleNamespace(committed=True, root_partition="/dev/sda2")
        dependencies = ValidationDependencies(
            parent_disk=lambda _partition: "/dev/sda",
            list_partitions=lambda _disk: [],
            probe_storage=lambda *_args, **_kwargs: snapshot,
            get_journal=lambda _context: journal,
        )
        self.assertEqual(
            _validate_install_target(
                {"disk": "/dev/sda", "install_mode": "manual"}, object(),
                snapshot=snapshot, dependencies=dependencies,
            ),
            ("/dev/sda", "/dev/sda2"),
        )
        cases = (
            ({"disk": "/dev/sda", "install_mode": "manual"}, None, "session context"),
            ({"disk": "/dev/sda", "install_mode": "alongside"}, object(), "No target partition"),
            ({"disk": "/dev/sda", "install_mode": "unknown"}, object(), "Unsupported"),
        )
        for config, context, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(RuntimeError, message):
                _validate_install_target(
                    config, context, snapshot=snapshot, dependencies=dependencies,
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

    def test_guided_validation_rejects_malformed_and_ambiguous_targets(self):
        ntfs_cases = (
            ({"resize_partition": "/dev/sda2", "resize_gib": 40}, self.snapshot(), "No target disk"),
            ({"disk": "/dev/sda", "resize_gib": 40}, self.snapshot(), "No NTFS partition"),
            ({"disk": "/dev/sda", "resize_partition": "/dev/sda2", "resize_gib": 1}, self.snapshot(), "at least"),
            ({"disk": "/dev/sdb", "resize_partition": "/dev/sda2", "resize_gib": 40}, self.snapshot(), "safe install target"),
        )
        for config, snapshot, message in ntfs_cases:
            with self.subTest(message=message), self.assertRaisesRegex(RuntimeError, message):
                validate_resize_ntfs_target(
                    config, snapshot=snapshot, dependencies=self.dependencies(),
                )

        free_cases = (
            ({"free_region_start": 0, "free_region_end": MIN_KYTHOS_BYTES}, "No target disk"),
            ({"disk": "/dev/sda", "free_region_start": 10, "free_region_end": 5}, "No free space"),
            ({"disk": "/dev/sda", "free_region_start": 1, "free_region_end": 1025}, "at least"),
            ({"disk": "/dev/sdb", "free_region_start": 1, "free_region_end": MIN_KYTHOS_BYTES + 1}, "safe install target"),
        )
        for config, message in free_cases:
            with self.subTest(message=message), self.assertRaisesRegex(RuntimeError, message):
                validate_free_space_target(
                    config, snapshot=self.snapshot(), dependencies=self.dependencies(),
                )

    def test_report_builder_covers_free_space_and_manual_capacity(self):
        start = 1024**2
        end = start + MIN_KYTHOS_BYTES
        free_snapshot = StorageSnapshot(
            disks=({"name": "/dev/sda"},), partitions=(),
            free_regions=({"start_bytes": start, "end_bytes": end},),
            efi_partition="/dev/sda1", is_gpt=False,
        )
        report = build_plan_report(
            {"disk": "/dev/sda", "install_mode": "free_space"},
            snapshot=free_snapshot, dependencies=self.report_dependencies(
                validate_free_space=lambda *_args, **_kwargs: ("/dev/sda", start, end)
            ),
        )
        self.assertTrue(report.valid)
        self.assertEqual(report.available_bytes, MIN_KYTHOS_BYTES)

        manual_snapshot = StorageSnapshot(
            disks=({"name": "/dev/sda"},),
            partitions=({"name": "/dev/sda2", "size_bytes": 80 * 1024**3},),
            free_regions=(), efi_partition="/dev/sda1", is_gpt=False,
        )
        report = build_plan_report(
            {"disk": "/dev/sda", "install_mode": "manual"},
            snapshot=manual_snapshot, dependencies=self.report_dependencies(
                validate_install=lambda *_args, **_kwargs: ("/dev/sda", "/dev/sda2")
            ),
        )
        self.assertTrue(report.valid)
        self.assertEqual(report.available_bytes, 80 * 1024**3)

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
