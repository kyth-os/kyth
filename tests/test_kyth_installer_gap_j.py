"""Gap J: validation.py coverage — hit missing lines for #1 fragile gap."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer.context import InstallerContext
from kyth_installer.validation import InstallRequestError, validate_install_request, _hash_password_for_request, _is_answer_file_request, validate_partition_install_request


def _base_body(**overrides):
    body = {
        "disk": "/dev/sda",
        "username": "kyth",
        "password": "secret",
        "hostname": "kyth-host",
        "confirm_backup": True,
        "confirm_erase": True,
    }
    body.update(overrides)
    return body


class ValidationGapJTests(unittest.TestCase):
    @patch("kyth_installer.validation.plan._validate_storage_intent")
    @patch("kyth_installer.validation.system._hash_password", return_value="hashed")
    @patch("kyth_installer.validation.system.list_timezones", return_value=["UTC"])
    @patch("kyth_installer.validation.system.list_locales", return_value=["en_US.UTF-8"])
    @patch("kyth_installer.validation.system.list_keymaps", return_value=["us"])
    @patch("kyth_installer.validation.disk.list_disks")
    def test_invalid_install_mode_hits_62(self, list_disks, *mocks):
        list_disks.return_value = [{"name": "/dev/sda", "current": False}]
        with self.assertRaisesRegex(InstallRequestError, "Invalid install mode"):
            validate_install_request(_base_body(install_mode="bogus"), InstallerContext())

    @patch("kyth_installer.validation.plan._validate_storage_intent")
    @patch("kyth_installer.validation.system._hash_password", return_value="hashed")
    @patch("kyth_installer.validation.system.list_timezones", return_value=["UTC"])
    @patch("kyth_installer.validation.system.list_locales", return_value=["en_US.UTF-8"])
    @patch("kyth_installer.validation.system.list_keymaps", return_value=["us"])
    @patch("kyth_installer.validation.disk.list_disks")
    def test_snapshot_exception_fallback_80_85_92_93(self, list_disks, *mocks):
        list_disks.return_value = [{"name": "/dev/sda", "current": False}]
        # Force exception branches in _storage_state snapshot building; fallback calls must succeed
        free_mock = MagicMock(side_effect=[RuntimeError("fail"), [{"start_bytes": 0, "end_bytes": 10*1024**3}]])
        efi_mock = MagicMock(side_effect=[RuntimeError("fail"), "/dev/sda1"])
        with patch("kyth_installer.validation.disk.list_partitions", side_effect=RuntimeError("fail")), \
             patch("kyth_installer.validation.disk.list_free_space", free_mock), \
             patch("kyth_installer.validation.disk.find_efi_partition", efi_mock), \
             patch("kyth_installer.validation.plan._is_gpt_disk", side_effect=RuntimeError("fail")):
            # free_space mode triggers _free and _is_gpt branches; fallback _free_regions/_efi succeed
            # Use 1M offset (0 is falsy via _safe_int) to hit valid region
            body = _base_body(install_mode="free_space", free_region_start=1048576, free_region_end=2097152)
            req = validate_install_request(body, InstallerContext())
            self.assertEqual(req.install_mode, "free_space")

    @patch("kyth_installer.validation.plan._validate_storage_intent")
    @patch("kyth_installer.validation.system._hash_password", return_value="hashed")
    @patch("kyth_installer.validation.system.list_timezones", return_value=["UTC"])
    @patch("kyth_installer.validation.system.list_locales", return_value=["en_US.UTF-8"])
    @patch("kyth_installer.validation.system.list_keymaps", return_value=["us"])
    @patch("kyth_installer.validation.disk.list_disks")
    def test_fallback_part_names_free_regions_efi_112_117_122(self, list_disks, *mocks):
        list_disks.return_value = [{"name": "/dev/sda", "current": False}]
        # _parts empty triggers _snapshot=None, so fallback closures are used
        with patch("kyth_installer.validation.disk.list_partitions", return_value=[]), \
             patch("kyth_installer.validation.disk.list_free_space", return_value=[{"start_bytes": 0, "end_bytes": 10*1024**3}]), \
             patch("kyth_installer.validation.disk.find_efi_partition", return_value="/dev/sda1"):
            # Invalid target_partition uses _part_names fallback -> empty set -> Invalid target partition
            with self.assertRaisesRegex(InstallRequestError, "Invalid target partition"):
                validate_install_request(_base_body(install_mode="alongside", target_partition="/dev/sda9"), InstallerContext())
            # free_space valid region uses _free_regions fallback (1M not 0 due to _safe_int falsy)
            body = _base_body(install_mode="free_space", free_region_start=1048576, free_region_end=2097152)
            # This will succeed in storage state, then validate -> need to mock plan validation already
            req = validate_install_request(body, InstallerContext())
            self.assertEqual(req.install_mode, "free_space")

    @patch("kyth_installer.validation.plan._validate_storage_intent")
    @patch("kyth_installer.validation.system._hash_password", return_value="hashed")
    @patch("kyth_installer.validation.system.list_timezones", return_value=["UTC"])
    @patch("kyth_installer.validation.system.list_locales", return_value=["en_US.UTF-8"])
    @patch("kyth_installer.validation.system.list_keymaps", return_value=["us"])
    @patch("kyth_installer.validation.disk.list_disks")
    def test_resize_ntfs_and_manual_and_current_disk_133_158(self, list_disks, *mocks):
        list_disks.return_value = [{"name": "/dev/sda", "current": False, "size_bytes": 100*1024**3}]
        # resize_ntfs invalid gib
        with patch("kyth_installer.validation.disk.list_partitions", return_value=[{"name": "/dev/sda2"}]), \
             patch("kyth_installer.validation.disk._safe_int", return_value=16):
            with self.assertRaisesRegex(InstallRequestError, "Invalid NTFS"):
                validate_install_request(_base_body(install_mode="resize_ntfs", resize_partition="/dev/sda2", resize_gib=16), InstallerContext())
        # manual without journal
        with patch("kyth_installer.validation.partition_ops.get_journal", return_value=None):
            with self.assertRaisesRegex(InstallRequestError, "Partition changes must be committed"):
                validate_install_request(_base_body(install_mode="manual"), InstallerContext())
        # manual with journal but no root
        mock_journal = MagicMock(committed=True, root_partition="")
        with patch("kyth_installer.validation.partition_ops.get_journal", return_value=mock_journal):
            with self.assertRaisesRegex(InstallRequestError, "No root partition"):
                validate_install_request(_base_body(install_mode="manual"), InstallerContext())
        # current disk check (config._IS_LIVE_SESSION False)
        list_disks.return_value = [{"name": "/dev/sda", "current": True}]
        with patch("kyth_installer.validation.config._IS_LIVE_SESSION", False):
            with self.assertRaisesRegex(InstallRequestError, "running the current"):
                validate_install_request(_base_body(install_mode="wipe"), InstallerContext())

    def test_hash_password_and_answer_file_and_locale_fallback_201_227_233(self):
        # _hash_password_for_request exception wrapping
        with patch("kyth_installer.validation.system._hash_password", side_effect=RuntimeError("boom")):
            with self.assertRaisesRegex(InstallRequestError, "Could not hash"):
                _hash_password_for_request("secret")
        # _is_answer_file_request
        self.assertFalse(_is_answer_file_request({}))
        # locale fallback strict False
        ctx = InstallerContext()
        ctx.state = {}
        with patch("kyth_installer.validation.disk.list_disks", return_value=[{"name": "/dev/sda", "current": False}]), \
             patch("kyth_installer.validation.plan._validate_storage_intent"), \
             patch("kyth_installer.validation.system._hash_password", return_value="hashed"), \
             patch("kyth_installer.validation.system.list_timezones", return_value=["UTC"]), \
             patch("kyth_installer.validation.system.list_locales", return_value=["en_US.UTF-8"]), \
             patch("kyth_installer.validation.system.list_keymaps", return_value=["us"]):
            req = validate_install_request(_base_body(timezone="Bad/Zone", locale="bad", keymap="bad"), ctx, strict_locale=False)
            self.assertEqual(req.timezone, "UTC")
            self.assertIn("locale_warnings", ctx.state)
        # partition request invalid EFI - hits line 290
        with patch("kyth_installer.validation.disk._normal_device_path", side_effect=lambda x: x), \
             patch("kyth_installer.validation.disk._parent_disk", return_value="/dev/sda"), \
             patch("kyth_installer.validation.disk.list_partitions", return_value=[{"name": "/dev/sda1", "efi": False}]):
            with self.assertRaisesRegex(InstallRequestError, "not an EFI"):
                validate_partition_install_request(target_partition="/dev/sda2", efi_partition="/dev/sda1", hostname="kyth", timezone="UTC", username="", password="", context=InstallerContext())
        # timezone invalid strict True hits 321
        with patch("kyth_installer.validation.disk._normal_device_path", return_value="/dev/sda2"), \
             patch("kyth_installer.validation.disk._parent_disk", return_value="/dev/sda"), \
             patch("kyth_installer.validation.disk.list_partitions", return_value=[{"name": "/dev/sda2"}]), \
             patch("kyth_installer.validation.plan._validate_storage_intent"), \
             patch("kyth_installer.validation.disk.find_efi_partition", return_value=""), \
             patch("kyth_installer.validation.plan._is_gpt_disk", return_value=False), \
             patch("kyth_installer.validation.disk.list_disks", return_value=[{"name": "/dev/sda", "current": False}]):
            with self.assertRaisesRegex(InstallRequestError, "Invalid timezone"):
                validate_partition_install_request(target_partition="/dev/sda2", efi_partition="", hostname="kyth", timezone="Bad/Zone", username="", password="", context=InstallerContext())


if __name__ == "__main__":
    unittest.main()
