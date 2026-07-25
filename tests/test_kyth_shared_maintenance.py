"""Unit tests for the shared maintenance module."""
from __future__ import annotations

import pathlib
import subprocess
import tempfile
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.maintenance import (
    cleanup_flatpaks,
    dedupe_directory,
    find_dedupe_targets,
    prune_trash,
    supports_dedupe,
    vacuum_user_journals,
)


class MaintenanceTests(unittest.TestCase):
    def test_prune_trash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = pathlib.Path(tmpdir)
            info_dir = tmp_path / ".local/share/Trash/info"
            files_dir = tmp_path / ".local/share/Trash/files"
            info_dir.mkdir(parents=True)
            files_dir.mkdir(parents=True)

            # Create a trashinfo file and target file
            trashinfo_file = info_dir / "test.trashinfo"
            # DeletionDate is 2026-07-20T14:30:00 (which is older than 1 day from now)
            trashinfo_file.write_text(
                "[Trash Info]\nPath=test\nDeletionDate=2026-07-20T14:30:00\n",
                encoding="utf-8"
            )
            target_file = files_dir / "test"
            target_file.write_text("deleted content", encoding="utf-8")

            with mock.patch("pathlib.Path.home", return_value=tmp_path):
                prune_trash(days=1)

            self.assertFalse(trashinfo_file.exists())
            self.assertFalse(target_file.exists())

    @mock.patch("subprocess.run")
    @mock.patch("shutil.which")
    def test_cleanup_flatpaks(self, mock_which, mock_run) -> None:
        mock_which.return_value = "/bin/flatpak"
        cleanup_flatpaks()
        mock_run.assert_called_once_with(
            ["flatpak", "uninstall", "--unused", "-y", "--noninteractive"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @mock.patch("subprocess.run")
    @mock.patch("shutil.which")
    def test_vacuum_user_journals(self, mock_which, mock_run) -> None:
        mock_which.return_value = "/bin/journalctl"
        vacuum_user_journals(days=30)
        mock_run.assert_called_once_with(
            ["journalctl", "--user", "--vacuum-time=30d"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @mock.patch("subprocess.run")
    @mock.patch("shutil.which")
    def test_supports_dedupe(self, mock_which, mock_run) -> None:
        mock_which.return_value = "/bin/findmnt"
        mock_run.return_value = mock.Mock(stdout="btrfs\n")
        self.assertTrue(supports_dedupe("/some/path"))

        mock_run.return_value = mock.Mock(stdout="ext4\n")
        self.assertFalse(supports_dedupe("/some/path"))

    @mock.patch("os.scandir")
    @mock.patch("pathlib.Path.is_dir")
    def test_find_dedupe_targets(self, mock_is_dir, mock_scandir) -> None:
        mock_is_dir.return_value = True

        # Mock nested entries
        mock_entry1 = mock.Mock()
        mock_entry1.is_dir.return_value = True
        mock_entry1.path = "/var/home/user/Steam/steamapps/compatdata"

        mock_scandir.return_value = [mock_entry1]

        targets = find_dedupe_targets("/var/home")
        self.assertIn("/var/home/user/Steam/steamapps/compatdata", targets)

    @mock.patch("subprocess.run")
    @mock.patch("shutil.which")
    def test_dedupe_directory(self, mock_which, mock_run) -> None:
        mock_which.side_effect = lambda c: f"/bin/{c}" if c in ("duperemove", "ionice") else None
        dedupe_directory("/some/dir")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("duperemove", args)
        self.assertIn("/some/dir", args)


if __name__ == "__main__":
    unittest.main()
