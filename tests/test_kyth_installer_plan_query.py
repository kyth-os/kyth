import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer import plan_query  # noqa: E402
from kyth_installer.config import BIOS_BOOT_BYTES, MIN_KYTHOS_BYTES  # noqa: E402


class PlanQueryTests(unittest.TestCase):
    def test_gpt_probe_uses_blkid_then_parted_fallback(self):
        run = mock.Mock(return_value=SimpleNamespace(stdout="gpt\n"))
        self.assertTrue(plan_query.is_gpt_disk("/dev/sda", run_command=run))

        run.side_effect = [RuntimeError("blkid failed"), SimpleNamespace(stdout="Partition Table: gpt")]
        self.assertTrue(plan_query.is_gpt_disk("/dev/sda", run_command=run))

        run.side_effect = RuntimeError("unavailable")
        self.assertFalse(plan_query.is_gpt_disk("/dev/sda", run_command=run))

    def test_bios_partition_and_required_space(self):
        self.assertTrue(plan_query.has_bios_boot_partition(
            "/dev/sda", list_partitions=lambda _disk: [{"parttype": "21686148-6449-6e6f-744e-656564454649"}],
        ))
        self.assertEqual(
            plan_query.required_guided_space(
                "/dev/sda", is_gpt=lambda _disk: True, has_bios_boot=lambda _disk: False,
            ),
            MIN_KYTHOS_BYTES + BIOS_BOOT_BYTES,
        )
        self.assertEqual(
            plan_query.required_guided_space(
                "/dev/sda", is_gpt=lambda _disk: False, has_bios_boot=lambda _disk: False,
            ),
            MIN_KYTHOS_BYTES,
        )

    def test_windows_suggestion_selects_largest_viable_ntfs_partition(self):
        snapshots = {
            "/dev/sda": SimpleNamespace(partitions_by_name={
                "/dev/sda1": {"fstype": "ntfs", "size_bytes": 128 * 1024**3},
            }),
            "/dev/sdb": SimpleNamespace(partitions_by_name={
                "/dev/sdb1": {"fstype": "ntfs", "size_bytes": 256 * 1024**3, "free_bytes": 80 * 1024**3},
            }),
        }
        result = plan_query.suggest_windows_resize_target(
            list_disks=lambda: [{"name": ""}, {"name": "/dev/sda"}, {"name": "/dev/sdb"}],
            probe_storage=lambda disk, **_kwargs: snapshots[disk],
        )
        self.assertEqual(result["partition"], "/dev/sdb1")

    def test_bootcurrent_discovery_handles_absence_errors_and_success(self):
        self.assertIsNone(plan_query.find_bootcurrent_esp(
            run_command=mock.Mock(), as_root=lambda argv: argv, which=lambda _name: None,
        ))
        output = "BootCurrent: 0002\nBoot0002* KythOS HD(1,GPT,uuid)\n"
        run = mock.Mock(return_value=SimpleNamespace(returncode=0, stdout=output))
        self.assertIn("Boot0002", plan_query.find_bootcurrent_esp(
            run_command=run, as_root=lambda argv: argv, which=lambda _name: "/usr/bin/efibootmgr",
        ))
        run.side_effect = RuntimeError("failed")
        self.assertIsNone(plan_query.find_bootcurrent_esp(
            run_command=run, as_root=lambda argv: argv, which=lambda _name: "yes",
        ))

    def test_manual_mounts_resolve_format_and_probed_filesystem(self):
        journal = SimpleNamespace(
            committed=True, disk="/dev/sda",
            ops=[
                {"kind": "set_mountpoint", "params": {"partition": "/dev/sda2", "mountpoint": "/home"}},
                {"kind": "format", "params": {"partition": "/dev/sda2", "fs_type": "xfs"}},
                {"kind": "set_mountpoint", "params": {"partition": "/dev/sda3", "mountpoint": "swap"}},
            ],
        )
        mounts = plan_query.get_manual_mounts(
            object(), get_journal=lambda _context: journal,
            list_partitions=lambda _disk: [{"name": "/dev/sda3", "fstype": "swap"}],
        )
        self.assertEqual(mounts[0]["fstype"], "xfs")
        self.assertEqual(mounts[1]["fstype"], "swap")
        self.assertEqual(plan_query.get_manual_mounts(
            object(), get_journal=lambda _context: None, list_partitions=lambda _disk: [],
        ), [])


if __name__ == "__main__":
    unittest.main()
