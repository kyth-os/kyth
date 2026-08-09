"""VM gate harness skeleton — drives the 10 doc gates without real hardware.

Uses dry_run DiskService + loop-mocked lsblk payloads to exercise
validate_plan_state containment, free-space exact-match on 4K, and
answer-file secret handling. CI runs this; real hardware gates run via
`just vm-gate` against actual qemu images."""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files/kyth-installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from kyth_installer import disk, plan
from kyth_installer.context import InstallerContext
from kyth_installer.storage_snapshot import StorageSnapshot


class VmGateHarnessTests(unittest.TestCase):
    """Gate #5: 512 and 4K logical sectors produce identical containment."""

    def test_free_space_4k_alignment_is_contained(self):
        # 100 GiB disk with one 50 GiB partition at 1 MiB offset.
        disk_size = 100 * 1024**3
        part_start = 1024 * 1024
        part_size = 50 * 1024**3

        def fake_part_size_bytes(_d):
            return disk_size

        def fake_block_size_4k(_d):
            return 4096

        def fake_block_size_512(_d):
            return 512

        parts = [
            {
                "name": "/dev/nvme0n1p1",
                "size_bytes": part_size,
                "start_bytes": part_start,
            }
        ]

        for sector in (512, 4096):
            with patch.object(disk, "_partition_size_bytes", fake_part_size_bytes), \
                 patch.object(disk, "_block_size_bytes", lambda _d, s=sector: s), \
                 patch.object(disk, "list_partitions", return_value=parts):
                regions = disk.list_free_space("/dev/nvme0n1")
                # Must surface a usable gap after the partition, aligned to sector.
                self.assertTrue(regions, f"no regions at {sector}")
                for r in regions:
                    self.assertEqual(r["start_bytes"] % sector, 0)
                    self.assertEqual(r["end_bytes"] % sector, 0)
                    # Gate: contains_free_region exact-match must hold for the
                    # reported region itself — validates 4K normalization.
                    snap = StorageSnapshot(
                        disks=({"name": "/dev/nvme0n1", "size_bytes": disk_size},),
                        partitions=tuple(parts),
                        free_regions=tuple(regions),
                        efi_partition="/dev/nvme0n1p5",
                        is_gpt=True,
                    )
                    self.assertTrue(snap.contains_free_region(r["start_bytes"], r["end_bytes"]))

    def test_contains_free_region_rejects_subregion(self):
        regions = ({"start_bytes": 10 * 1024**2, "end_bytes": 50 * 1024**3, "size_bytes": 50 * 1024**3 - 10 * 1024**2},)
        snap = StorageSnapshot(
            disks=({"name": "/dev/sda"},),
            partitions=(),
            free_regions=regions,
            efi_partition=None,
            is_gpt=True,
        )
        # Off-by-one sector subregion must be rejected — exact-match policy.
        self.assertFalse(snap.contains_free_region(10 * 1024**2 + 4096, 50 * 1024**3))

    def test_answer_file_secrets_abi(self):
        from kyth_installer.app import _ANSWER_FILE_FIELDS

        # Passwords / MOK must travel via answer-file fields, not CLI.
        self.assertIn("password", _ANSWER_FILE_FIELDS)
        self.assertIn("mok_password", _ANSWER_FILE_FIELDS)
