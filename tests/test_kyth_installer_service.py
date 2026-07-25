import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files/kyth-installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from kyth_installer.context import InstallerContext
from kyth_installer.services.installer_service import InstallerService
from kyth_installer.app import run_headless


class TestInstallerService(unittest.TestCase):
    def setUp(self):
        self.context = InstallerContext()
        self.service = InstallerService(self.context)

    @patch("kyth_installer.disk.list_disks")
    def test_new_table(self, mock_list_disks):
        mock_list_disks.return_value = [{"name": "/dev/sda"}]
        body = {"disk": "/dev/sda", "table_type": "gpt"}
        
        # Test valid disk and table type
        res = self.service.new_table(body)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("pending"), 1)
        
        # Test invalid disk
        body_invalid = {"disk": "/dev/sdb", "table_type": "gpt"}
        res_invalid = self.service.new_table(body_invalid)
        self.assertFalse(res_invalid.get("ok"))

    @patch("kyth_installer.disk.list_disks")
    @patch("kyth_installer.system.list_timezones")
    def test_start_install_validations(self, mock_timezones, mock_list_disks):
        mock_list_disks.return_value = [{"name": "/dev/sda"}]
        mock_timezones.return_value = ["UTC", "America/New_York"]
        
        # Invalid username
        body = {
            "disk": "/dev/sda",
            "install_mode": "wipe",
            "username": "INVALID USERNAME",
            "password": "password",
            "hostname": "kyth",
            "confirm_backup": True,
            "confirm_erase": True,
        }
        res = self.service.start_install(body)
        self.assertFalse(res.get("started"))
        
        # Invalid hostname
        body["username"] = "validuser"
        body["hostname"] = "invalid_hostname_!!!"
        res = self.service.start_install(body)
        self.assertFalse(res.get("started"))

    @patch("sys.argv", ["/path/to/cmd", "--headless"])
    @patch("kyth_installer.services.installer_service.InstallerService")
    def test_headless_cli_entrypoint(self, mock_service_class):
        
        mock_service = MagicMock()
        mock_service.start_install.return_value = {"started": False, "message": "Failed to start"}
        mock_service_class.return_value = mock_service

        with patch("argparse.ArgumentParser.parse_known_args") as mock_parse:
            mock_args = MagicMock()
            mock_args.disk = "/dev/sda"
            mock_args.install_mode = "wipe"
            mock_args.username = "user"
            mock_args.password = "pass"
            mock_args.hostname = "kyth"
            mock_args.timezone = "UTC"
            mock_args.kernel = "fedora"
            mock_args.mok_password = ""
            mock_args.confirm_backup = True
            mock_args.confirm_erase = True
            mock_args.confirm_current = True
            mock_parse.return_value = (mock_args, [])
            
            with self.assertRaises(SystemExit) as cm:
                run_headless()
            self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
