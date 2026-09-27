"""Extra coverage for plan_commit branches missing from main tests."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files/kyth-installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from kyth_installer import plan_commit
from kyth_installer.plan_commit import CommitDependencies


def _dummy_deps(**overrides):
    base = dict(
        is_gpt=lambda d: True,
        has_bios_boot=lambda d: False,
        list_partitions=lambda d: [],
        block_size=lambda d: 512,
        latest_partition=lambda d, before: None,
        partition_number=lambda p: 1,
        human_size=lambda n: f"{n}B",
        run_command=lambda *a, **k: MagicMock(returncode=0),
        as_root=lambda c: c,
        settle=lambda: None,
        disk_hold=lambda d, l: MagicMock(__enter__=lambda s: None, __exit__=lambda s, *a: False),
        guard_factory=lambda d, l, disk_service=None: MagicMock(__enter__=lambda s: None, __exit__=lambda s, *a: False),
        disk_service_factory=lambda: MagicMock(),
    )
    base.update(overrides)
    return CommitDependencies(**base)


class BiosBootGuardOSErrorTests(unittest.TestCase):
    def test_battery_oserror_is_logged_and_continues(self):
        # lines 47-50: _battery_check OSError -> debug, not raise
        with patch("kyth_installer.assurance._battery_check", side_effect=OSError("probe down"), create=True):
            deps = _dummy_deps(
                is_gpt=lambda d: False,  # early return, but guard still probed first
                has_bios_boot=lambda d: False,
            )
            # is_gpt False -> returns gap_start without creating; OSError path exercised
            result = plan_commit.ensure_bios_boot_partition("/dev/sda", 1048576, lambda m: None, dependencies=deps)
            self.assertEqual(result, 1048576)


class CommitVisibleWarnTests(unittest.TestCase):
    def test_created_not_visible_logs_warning(self):
        # lines 151-155: created not in visible -> warning log
        created = "/dev/sda3"
        deps = _dummy_deps(
            list_partitions=lambda d: [{"name": created}] if d == "/dev/sda" else [],
            latest_partition=lambda d, before: created,
            block_size=lambda d: 512,
            is_gpt=lambda d: True,
            has_bios_boot=lambda d: True,  # skip bios creation
            run_command=lambda *a, **k: MagicMock(returncode=0),
        )
        # Make second list_partitions call (visible check) return different set without created
        call_count = {"n": 0}
        def list_side(d):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return []  # before
            return [{"name": "/dev/sda1"}]  # visible without created -> triggers warn
        deps2 = _dummy_deps(
            list_partitions=list_side,
            latest_partition=lambda d, before: created,
            block_size=lambda d: 512,
            is_gpt=lambda d: True,
            has_bios_boot=lambda d: True,
            run_command=lambda *a, **k: MagicMock(returncode=0),
        )
        logs = []
        result = plan_commit.commit_new_kythos_partition("/dev/sda", 0, 10*1024**3, logs.append, dependencies=deps2)
        self.assertEqual(result, created)
        self.assertTrue(any("did not yet expose" in m for m in logs))

    def test_verify_exception_logs_warning(self):
        # line 156-157 except Exception -> log
        created = "/dev/sda3"
        def bad_list(d):
            raise RuntimeError("probe failed")
        deps = _dummy_deps(
            list_partitions=bad_list,
            latest_partition=lambda d, before: created,
            block_size=lambda d: 512,
            is_gpt=lambda d: True,
            has_bios_boot=lambda d: True,
            run_command=lambda *a, **k: MagicMock(returncode=0),
        )
        # Need first list to succeed for before set, then second to fail for verify
        calls = {"n": 0}
        def list_mixed(d):
            calls["n"] += 1
            if calls["n"] == 1:
                return []
            if calls["n"] == 2:
                raise RuntimeError("verify probe failed")
            return [{"name": created}]
        deps2 = _dummy_deps(
            list_partitions=list_mixed,
            latest_partition=lambda d, before: created,
            block_size=lambda d: 512,
            is_gpt=lambda d: True,
            has_bios_boot=lambda d: True,
            run_command=lambda *a, **k: MagicMock(returncode=0),
        )
        logs = []
        result = plan_commit.commit_new_kythos_partition("/dev/sda", 0, 10*1024**3, logs.append, dependencies=deps2)
        self.assertEqual(result, created)
        self.assertTrue(any("could not verify" in m for m in logs))


class NtfsMarkerProbeTests(unittest.TestCase):
    def test_marker_probe_oserror_is_debug_and_continues(self):
        # lines 239-240: marker.is_file OSError -> debug, then continues to validate_target
        with patch("pathlib.Path.is_file", side_effect=OSError("probe failed")):
            # minimal validate_target returning disk/partition
            def fake_validate(cfg):
                return ("/dev/sda", "/dev/sda2", 1*1024**3)
            logs = []
            # need deps that won't fail later; use real function but mock unmount/commit to no-op
            result_disk, result_create = plan_commit.prepare_ntfs_resize_target(
                {"resize_partition": "/dev/sda2"},
                logs.append,
                normal_device_path=lambda p: p,
                validate_target=fake_validate,
                required_tools=[],
                which=lambda c: "/usr/bin/" + c,
                unmount_target_disk=lambda d, l: None,
                partition_size=lambda p: 10*1024**3,
                partition_number=lambda p: 2,
                block_size=lambda d: 512,
                partition_start=lambda p: 0,
                shrink_filesystem_guarded=lambda *a, **k: None,
                run_command=lambda *a, **k: MagicMock(returncode=0),
                as_root=lambda c: c,
                settle=lambda: None,
                commit_partition=lambda *a, **k: "/dev/sda3",
            )
            self.assertEqual(result_create, "/dev/sda3")


if __name__ == "__main__":
    unittest.main()
