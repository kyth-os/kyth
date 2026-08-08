"""Unit tests for the shared drives/NTFS repair module."""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.system.drives import get_ntfs_devices, repair_ntfs_drives


class DrivesTests(unittest.TestCase):
    @mock.patch("subprocess.run")
    def test_get_ntfs_devices_empty(self, mock_run) -> None:
        mock_run.return_value = mock.Mock(returncode=0, stdout='{"blockdevices": []}')
        devices = get_ntfs_devices()
        self.assertEqual(devices, [])

    @mock.patch("subprocess.run")
    def test_get_ntfs_devices_with_partitions(self, mock_run) -> None:
        lsblk_json = """{
            "blockdevices": [
                {
                    "name": "sda",
                    "fstype": null,
                    "children": [
                        {"name": "sda1", "fstype": "ntfs", "label": "Games", "uuid": "1234-5678", "mountpoint": "/mnt/games"},
                        {"name": "sda2", "fstype": "ext4", "label": "Linux", "uuid": "8765-4321", "mountpoint": "/"}
                    ]
                }
            ]
        }"""
        mock_run.return_value = mock.Mock(returncode=0, stdout=lsblk_json)
        devices = get_ntfs_devices()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["name"], "sda1")
        self.assertEqual(devices[0]["fstype"], "ntfs")

    @mock.patch("pathlib.Path.home")
    @mock.patch("subprocess.run")
    def test_repair_ntfs_drives(self, mock_run, mock_home) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = pathlib.Path(tmpdir)
            mock_home.return_value = temp_path

            # Create native steamapps/compatdata directory
            native_compatdata = temp_path / ".local" / "share" / "Steam" / "steamapps" / "compatdata"
            native_compatdata.mkdir(parents=True, exist_ok=True)
            # Create a file inside it to simulate existing prefixes
            (native_compatdata / "123").touch()

            # Create a mock NTFS mount directory with steamapps
            ntfs_mount = temp_path / "ntfs_drive"
            steamapps_dir = ntfs_mount / "SteamLibrary" / "steamapps"
            steamapps_dir.mkdir(parents=True, exist_ok=True)
            compatdata_dir = steamapps_dir / "compatdata"
            compatdata_dir.mkdir()
            (compatdata_dir / "old_prefix").touch()

            # Mock lsblk json to return the mounted NTFS partition
            lsblk_json = f"""{{
                "blockdevices": [
                    {{"name": "sdb1", "fstype": "ntfs", "label": "WinGames", "uuid": "abcd-efgh", "mountpoint": "{ntfs_mount}"}}
                ]
            }}"""
            
            # Setup subprocess mock
            def run_side_effect(args, **kwargs):
                if "lsblk" in args:
                    return mock.Mock(returncode=0, stdout=lsblk_json)
                return mock.Mock(returncode=0)
            mock_run.side_effect = run_side_effect

            # Run repair
            repair_ntfs_drives()

            # The original compatdata directory should be moved to a backup (compatdata.bak.*)
            # and replaced with a symlink to native_compatdata
            self.assertTrue(compatdata_dir.is_symlink())
            self.assertEqual(compatdata_dir.resolve(), native_compatdata)

            # Check that a backup directory was created
            backups = list(steamapps_dir.glob("compatdata.bak.*"))
            self.assertEqual(len(backups), 1)
            self.assertTrue((backups[0] / "old_prefix").is_file())


if __name__ == "__main__":
    unittest.main()
