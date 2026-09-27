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
            list_partitions=lambda _disk: [
                {"name": "/dev/sda2", "fstype": "ext4"},
                {"name": "/dev/sda3", "fstype": "swap"},
            ],
        )
        self.assertEqual(mounts[0]["fstype"], "xfs")
        self.assertEqual(mounts[1]["fstype"], "swap")
        self.assertEqual(plan_query.get_manual_mounts(
            object(), get_journal=lambda _context: None, list_partitions=lambda _disk: [],
        ), [])

    def test_manual_mounts_fail_closed_on_stale_duplicate_or_malformed_journal(self):
        def journal(ops, disk="/dev/sda"):
            return SimpleNamespace(committed=True, disk=disk, ops=ops)

        with self.assertRaisesRegex(RuntimeError, "disappeared"):
            plan_query.get_manual_mounts(
                object(), get_journal=lambda _context: journal([{
                    "kind": "set_mountpoint",
                    "params": {"partition": "/dev/sda9", "mountpoint": "/home"},
                }]), list_partitions=lambda _disk: [],
            )

        duplicate = [
            {"kind": "set_mountpoint", "params": {
                "partition": "/dev/sda2", "mountpoint": "/home",
            }},
            {"kind": "set_mountpoint", "params": {
                "partition": "/dev/sda3", "mountpoint": "/home",
            }},
        ]
        with self.assertRaisesRegex(RuntimeError, "assigned more than once"):
            plan_query.get_manual_mounts(
                object(), get_journal=lambda _context: journal(duplicate),
                list_partitions=lambda _disk: [
                    {"name": "/dev/sda2"}, {"name": "/dev/sda3"},
                ],
            )

        with self.assertRaisesRegex(RuntimeError, "malformed"):
            plan_query.get_manual_mounts(
                object(), get_journal=lambda _context: journal([{"kind": "create"}]),
                list_partitions=lambda _disk: [],
            )

    def test_suggest_windows_filters_exceptions_and_small_or_wrong_fstype(self):
        # probe raises for one disk, ext4 and undersized ntfs are skipped
        snapshots = {
            "/dev/sdb": SimpleNamespace(partitions_by_name={
                "/dev/sdb1": {"fstype": "ext4", "size_bytes": 200 * 1024**3},
                "/dev/sdb2": {"fstype": "ntfs", "size_bytes": 50 * 1024**3},
                "/dev/sdb3": {"fstype": "ntfs", "size_bytes": 200 * 1024**3},
            }),
        }

        def probe(name, **_kwargs):
            if name == "/dev/sda":
                raise RuntimeError("probe failed")
            return snapshots[name]

        result = plan_query.suggest_windows_resize_target(
            list_disks=lambda: [{"name": "/dev/sda"}, {"name": "/dev/sdb"}],
            probe_storage=probe,
        )
        self.assertEqual(result["partition"], "/dev/sdb3")

    def test_bootcurrent_returns_none_on_nonzero_or_empty_or_no_match(self):
        # non-zero returncode
        run = mock.Mock(return_value=SimpleNamespace(returncode=1, stdout="BootCurrent: 0001\n"))
        self.assertIsNone(plan_query.find_bootcurrent_esp(run_command=run, as_root=lambda v: v, which=lambda _: "/usr/bin/efibootmgr"))
        # empty stdout
        run = mock.Mock(return_value=SimpleNamespace(returncode=0, stdout=""))
        self.assertIsNone(plan_query.find_bootcurrent_esp(run_command=run, as_root=lambda v: v, which=lambda _: "/usr/bin/efibootmgr"))
        # no BootCurrent match
        run = mock.Mock(return_value=SimpleNamespace(returncode=0, stdout="BootOrder: 0001\nBoot0001* something\n"))
        self.assertIsNone(plan_query.find_bootcurrent_esp(run_command=run, as_root=lambda v: v, which=lambda _: "/usr/bin/efibootmgr"))

    def test_manual_mounts_validates_empty_disk_and_skips_root_and_duplicate_partition(self):
        def journal(ops, disk="/dev/sda"):
            return SimpleNamespace(committed=True, disk=disk, ops=ops)

        with self.assertRaisesRegex(RuntimeError, "no target disk"):
            plan_query.get_manual_mounts(
                object(), get_journal=lambda _c: journal([], disk=""), list_partitions=lambda _d: []
            )
        # root and /boot/efi are skipped, leaving only /home
        ops = [
            {"kind": "set_mountpoint", "params": {"partition": "/dev/sda2", "mountpoint": "/"}},
            {"kind": "set_mountpoint", "params": {"partition": "/dev/sda3", "mountpoint": "/boot/efi"}},
            {"kind": "set_mountpoint", "params": {"partition": "/dev/sda4", "mountpoint": ""}},
            {"kind": "set_mountpoint", "params": {"partition": "/dev/sda5", "mountpoint": "/home"}},
        ]
        mounts = plan_query.get_manual_mounts(
            object(), get_journal=lambda _c: journal(ops), list_partitions=lambda _d: [{"name": "/dev/sda5", "fstype": "btrfs"}]
        )
        self.assertEqual(len(mounts), 1)
        self.assertEqual(mounts[0]["mountpoint"], "/home")

        # duplicate partition assignment
        duplicate_part = [
            {"kind": "set_mountpoint", "params": {"partition": "/dev/sda2", "mountpoint": "/home"}},
            {"kind": "set_mountpoint", "params": {"partition": "/dev/sda2", "mountpoint": "/data"}},
        ]
        with self.assertRaisesRegex(RuntimeError, "multiple mount assignments"):
            plan_query.get_manual_mounts(
                object(), get_journal=lambda _c: journal(duplicate_part),
                list_partitions=lambda _d: [{"name": "/dev/sda2"}],
            )


if __name__ == "__main__":
    unittest.main()
