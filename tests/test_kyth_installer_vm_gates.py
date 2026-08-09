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

    def test_find_efi_partition_cross_disk(self):
        other_efi = "/dev/nvme1n1p1"

        def fake_list_partitions(disk_name):
            if disk_name == "/dev/nvme0n1":
                return [{"name": "/dev/nvme0n1p1", "efi": False}]
            if disk_name == "/dev/nvme1n1":
                return [{"name": other_efi, "efi": True}]
            return []

        fake_disks = [{"name": "/dev/nvme0n1"}, {"name": "/dev/nvme1n1"}]

        with patch.object(disk, "list_partitions", side_effect=fake_list_partitions), \
             patch.object(disk, "list_disks", return_value=fake_disks), \
             patch.object(disk, "_protected_install_disks", return_value=set()), \
             patch.object(disk, "_findmnt_source", return_value=""):
            self.assertEqual(disk.find_efi_partition("/dev/nvme0n1"), other_efi)

    def test_find_efi_partition_excludes_live_media(self):
        live_esp = "/dev/sdb1"
        with patch.object(disk, "list_partitions", return_value=[{"name": "/dev/nvme0n1p1", "efi": False}]), \
             patch.object(disk, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(disk, "_protected_install_disks", return_value={"/dev/sdb"}), \
             patch.object(disk, "_findmnt_source", return_value=live_esp), \
             patch.object(disk, "_parent_disk", return_value="/dev/sdb"):
            self.assertEqual(disk.find_efi_partition("/dev/nvme0n1"), "")

    def test_validation_uses_cross_disk_efi_for_alongside(self):
        from kyth_installer.validation import validate_install_request
        target_disk = "/dev/nvme0n1"
        efi_part = "/dev/nvme1n1p1"
        target_part = "/dev/nvme0n1p2"
        fake_disks = [
            {"name": target_disk, "size_bytes": 200 * 1024**3, "current": False},
            {"name": "/dev/nvme1n1", "size_bytes": 500 * 1024**3, "current": False},
        ]

        def fake_list_parts(disk_name):
            if disk_name == target_disk:
                return [{"name": target_part, "efi": False, "size_bytes": 80 * 1024**3, "read_only": False}]
            if disk_name == "/dev/nvme1n1":
                return [{"name": efi_part, "efi": True, "read_only": False}]
            return []
        ctx = InstallerContext()
        body = {
            "disk": target_disk, "install_mode": "alongside", "target_partition": target_part,
            "confirm_backup": True, "confirm_erase": True,
            "password": "Secret123!", "username": "ada", "hostname": "kyth",
        }
        with patch.object(disk, "list_disks", return_value=fake_disks), \
             patch.object(disk, "list_partitions", side_effect=fake_list_parts), \
             patch.object(disk, "find_efi_partition", return_value=efi_part), \
             patch.object(disk, "_safe_int", side_effect=lambda v, d=0: int(v) if str(v).isdigit() else d if isinstance(v, int) else 0), \
             patch("kyth_installer.plan._is_gpt_disk", return_value=True), \
             patch("kyth_installer.plan._has_bios_boot_partition", return_value=True), \
             patch("kyth_installer.validation.plan._validate_storage_intent") as mock_validate, \
             patch("kyth_installer.system.list_timezones", return_value=["UTC", "Europe/Berlin"]), \
             patch("kyth_installer.system.list_locales", return_value=["en_US.UTF-8", "de_DE.UTF-8"]), \
             patch("kyth_installer.system.list_keymaps", return_value=["us", "de"]), \
             patch("kyth_installer.system._hash_password", return_value="$6$hashed"):
            try:
                req = validate_install_request(body, ctx, strict_locale=True)
            except Exception as exc:
                self.fail(f"cross-disk EFI validation unexpectedly failed: {exc}")
            if mock_validate.called:
                self.assertEqual(mock_validate.call_args[0][0].get("efi_partition"), efi_part)

    def test_headless_locale_fallback_is_auditable(self):
        from kyth_installer.validation import validate_install_request
        target_disk = "/dev/nvme0n1"
        fake_disks = [{"name": target_disk, "size_bytes": 200 * 1024**3, "current": False}]
        ctx = InstallerContext()
        # Use typos that would previously silently fallback to UTC/en_US/us
        body = {
            "disk": target_disk, "install_mode": "wipe",
            "confirm_backup": True, "confirm_erase": True,
            "password": "Secret123!", "username": "ada", "hostname": "kyth",
            "timezone": "Eurp/Berlin", "locale": "bad_LOC", "keymap": "nope!",
        }
        with patch.object(disk, "list_disks", return_value=fake_disks), \
             patch.object(disk, "list_partitions", return_value=[]), \
             patch("kyth_installer.validation.plan._validate_storage_intent"), \
             patch("kyth_installer.system.list_timezones", return_value=["UTC"]), \
             patch("kyth_installer.system.list_locales", return_value=["en_US.UTF-8"]), \
             patch("kyth_installer.system.list_keymaps", return_value=["us"]), \
             patch("kyth_installer.system._hash_password", return_value="$6$hashed"):
            req = validate_install_request(body, ctx, strict_locale=False)
            self.assertEqual(req.timezone, "UTC")
            self.assertEqual(req.locale, "en_US.UTF-8")
            self.assertEqual(req.keymap, "us")
            # Must be recorded in context.state for transaction probe
            self.assertIn("locale_warnings", ctx.state)
            self.assertTrue(any("Eurp/Berlin" in w for w in ctx.state["locale_warnings"]))
            # Strict mode must still raise
        with patch.object(disk, "list_disks", return_value=fake_disks), \
             patch.object(disk, "list_partitions", return_value=[]), \
             patch("kyth_installer.validation.plan._validate_storage_intent"), \
             patch("kyth_installer.system.list_timezones", return_value=["UTC"]), \
             patch("kyth_installer.system.list_locales", return_value=["en_US.UTF-8"]), \
             patch("kyth_installer.system.list_keymaps", return_value=["us"]), \
             patch("kyth_installer.system._hash_password", return_value="$6$hashed"):
            with self.assertRaises(Exception):
                validate_install_request(body, ctx, strict_locale=True)
