import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

import kyth_installer.disk as disk  # noqa: E402
from kyth_installer.disk import _lookup, _util  # noqa: E402


class InstallerDiskLookupCoverageTests(unittest.TestCase):
    def test_find_efi_prefers_partition_on_selected_disk(self):
        with mock.patch.object(disk, "list_partitions", return_value=[
            {"name": "/dev/sda1", "efi": False},
            {"name": "/dev/sda2", "efi": True},
        ]), mock.patch.object(disk, "list_disks") as list_disks:
            self.assertEqual(_lookup.find_efi_partition("/dev/sda"), "/dev/sda2")
        list_disks.assert_not_called()

    def test_find_efi_uses_other_disks_before_mount_fallback(self):
        def partitions(device):
            return [{"name": f"{device}1", "efi": device == "/dev/sdb"}]

        with mock.patch.object(disk, "list_partitions", side_effect=partitions), mock.patch.object(
            disk, "list_disks", return_value=[{"name": "/dev/sda"}, {"name": "/dev/sdb"}]
        ):
            self.assertEqual(_lookup.find_efi_partition("/dev/sda"), "/dev/sdb1")

    def test_find_efi_mount_fallback_skips_protected_system_disk(self):
        with mock.patch.object(disk, "list_partitions", return_value=[]), mock.patch.object(
            disk, "list_disks", side_effect=OSError("probe failed")
        ), mock.patch.object(disk, "_protected_install_disks", return_value={"/dev/sda"}), mock.patch.object(
            disk, "_findmnt_source", side_effect=["/dev/sda1", "/dev/sdb1"]
        ), mock.patch.object(disk, "_parent_disk", side_effect=["/dev/sda", "/dev/sdb"]):
            self.assertEqual(_lookup.find_efi_partition("/dev/sdc"), "/dev/sdb1")

    def test_find_efi_returns_empty_when_protection_or_mount_probes_fail(self):
        with mock.patch.object(disk, "list_partitions", return_value=[]), mock.patch.object(
            disk, "list_disks", return_value=[]
        ), mock.patch.object(disk, "_protected_install_disks", side_effect=RuntimeError):
            self.assertEqual(_lookup.find_efi_partition("/dev/sda"), "")

        with mock.patch.object(disk, "list_partitions", return_value=[]), mock.patch.object(
            disk, "list_disks", return_value=[]
        ), mock.patch.object(disk, "_protected_install_disks", return_value=set()), mock.patch.object(
            disk, "_findmnt_source", side_effect=RuntimeError
        ):
            self.assertEqual(_lookup.find_efi_partition("/dev/sda"), "")

    def test_root_partition_selects_largest_lsblk_partition(self):
        payload = {"blockdevices": [{"children": [
            {"name": "sda1", "size": 1024, "type": "part"},
            {"name": "sda2", "size": 4096, "type": "part"},
            {"name": "crypt", "size": 8192, "type": "crypt"},
        ]}]}
        with mock.patch.object(disk, "run_command", return_value=SimpleNamespace(stdout=json.dumps(payload))):
            self.assertEqual(_lookup.get_root_partition("/dev/sda"), "/dev/sda2")

    def test_root_partition_falls_back_to_matching_btrfs_blkid(self):
        responses = [OSError("lsblk failed"), SimpleNamespace(stdout="/dev/sdb1\n/dev/sda3\n")]
        with mock.patch.object(disk, "run_command", side_effect=responses):
            self.assertEqual(_lookup.get_root_partition("/dev/sda"), "/dev/sda3")

    def test_root_partition_reports_when_both_probes_fail(self):
        with mock.patch.object(disk, "run_command", side_effect=OSError("failed")):
            with self.assertRaisesRegex(RuntimeError, "lsblk and blkid both failed"):
                _lookup.get_root_partition("/dev/sda")

    def test_lsblk_helpers_handle_success_failure_and_non_device_mounts(self):
        with mock.patch.object(disk, "run_command", return_value=SimpleNamespace(stdout=" disk \n")):
            self.assertEqual(_util._lsblk_text(["-n"]), "disk")
        with mock.patch.object(disk, "run_command", side_effect=OSError):
            self.assertEqual(_util._lsblk_text(["-n"]), "")
        with mock.patch.object(disk, "run_command", return_value=SimpleNamespace(stdout="overlay\n")):
            self.assertEqual(_util._findmnt_source("/"), "")

    def test_lsblk_tree_flattens_children_and_normalizes_parents(self):
        devices = [{
            "name": "/dev/sda",
            "type": "disk",
            "children": [{"name": "/dev/sda1", "pkname": "/dev/sda", "type": "part"}],
        }]
        with mock.patch.object(disk, "_lsblk_blockdevices", return_value=devices):
            tree = _util._lsblk_tree()
        self.assertEqual(tree["/dev/sda"]["type"], "disk")
        self.assertEqual(tree["/dev/sda1"]["pkname"], "/dev/sda")
        with mock.patch.object(disk, "_lsblk_blockdevices", side_effect=OSError):
            self.assertEqual(_util._lsblk_tree(), {})

    def test_device_type_and_block_sector_size_are_conservative(self):
        with mock.patch.object(disk, "_lsblk_text", return_value="part\nextra"):
            self.assertEqual(_util._device_type("sda1"), "part")
        self.assertEqual(_util._device_type(None), "")
        with mock.patch.object(disk, "run_command", return_value=SimpleNamespace(stdout="4096\n")):
            self.assertEqual(_util._block_size_bytes("/dev/sda"), 4096)
        with mock.patch.object(disk, "run_command", return_value=SimpleNamespace(stdout="128\n")):
            self.assertEqual(_util._block_size_bytes("/dev/sda"), 512)
        with mock.patch.object(disk, "run_command", side_effect=OSError):
            self.assertEqual(_util._block_size_bytes("/dev/sda"), 512)


if __name__ == "__main__":
    unittest.main()
