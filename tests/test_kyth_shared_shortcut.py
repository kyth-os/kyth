"""Unit tests for the shared desktop shortcut module."""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.desktop.shortcut import (
    categorize_web_apps,
    copy_steam_icon,
    export_steam_games,
    refresh_desktop_database,
    refresh_icon_cache,
    refresh_kde_sycoca,
    rewrite_steam_exec,
    safe_id,
)


class ShortcutTests(unittest.TestCase):
    def test_safe_id(self) -> None:
        self.assertEqual(safe_id("Steam Launcher"), "steam-launcher")
        self.assertEqual(safe_id("VLC Media Player!!"), "vlc-media-player")
        self.assertEqual(safe_id("--test--"), "test")

    def test_rewrite_steam_exec(self) -> None:
        exec_rungame = "Exec=steam://rungameid/12345"
        self.assertEqual(
            rewrite_steam_exec(exec_rungame),
            "Exec=flatpak run com.valvesoftware.Steam steam://rungameid/12345"
        )

        exec_launch = "Exec=/usr/bin/steam -applaunch 67890"
        self.assertEqual(
            rewrite_steam_exec(exec_launch),
            "Exec=flatpak run com.valvesoftware.Steam steam://rungameid/67890"
        )

        exec_other = "Exec=dolphin"
        self.assertIsNone(rewrite_steam_exec(exec_other))

    def test_copy_steam_icon(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = pathlib.Path(tmpdir)
            src = tmp_path / "src"
            dst = tmp_path / "dst"

            # Create a source icon in src/apps/testicon.png
            icon_file = src / "apps" / "testicon.png"
            icon_file.parent.mkdir(parents=True)
            icon_file.write_text("fake icon", encoding="utf-8")

            self.assertTrue(copy_steam_icon("testicon", src, dst))
            self.assertTrue((dst / "apps" / "testicon.png").is_file())

    @mock.patch("pathlib.Path.glob")
    @mock.patch("pathlib.Path.is_dir")
    @mock.patch("subprocess.run")
    @mock.patch("shutil.which")
    def test_export_steam_games(self, mock_which, mock_run, mock_is_dir, mock_glob) -> None:
        mock_which.return_value = "/bin/update-desktop-database"
        mock_is_dir.return_value = True

        mock_app = mock.Mock()
        mock_app.name = "test.desktop"
        mock_app.glob.return_value = []

        mock_glob.return_value = [mock_app]

        desktop_content = (
            "[Desktop Entry]\n"
            "Name=Test Game\n"
            "Exec=steam://rungameid/999\n"
            "Icon=testgame\n"
            "Categories=Game;\n"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            data_home = pathlib.Path(tmpdir) / "data"
            with (
                mock.patch.dict(os.environ, {"HOME": tmpdir, "XDG_DATA_HOME": str(data_home)}),
                mock.patch("builtins.open", mock.mock_open(read_data=desktop_content)),
            ):
                exported, skipped = export_steam_games()
                self.assertEqual(exported, 1)
                self.assertEqual(skipped, 0)

    @mock.patch("subprocess.run")
    @mock.patch("shutil.which")
    def test_refresh_desktop_database(self, mock_which, mock_run) -> None:
        mock_which.return_value = "/usr/bin/update-desktop-database"
        refresh_desktop_database("/tmp/apps")
        mock_run.assert_called_once_with(
            ["update-desktop-database", "/tmp/apps"], capture_output=True, check=False, timeout=30
        )

    @mock.patch("subprocess.run")
    @mock.patch("shutil.which")
    def test_refresh_desktop_database_missing_binary(self, mock_which, mock_run) -> None:
        mock_which.return_value = None
        refresh_desktop_database("/tmp/apps")
        mock_run.assert_not_called()

    @mock.patch("subprocess.run")
    @mock.patch("shutil.which")
    def test_refresh_icon_cache(self, mock_which, mock_run) -> None:
        mock_which.return_value = "/usr/bin/gtk-update-icon-cache"
        refresh_icon_cache("/tmp/icons")
        mock_run.assert_called_once_with(
            ["gtk-update-icon-cache", "-q", "-t", "/tmp/icons"], capture_output=True, check=False, timeout=30
        )

    @mock.patch("subprocess.run")
    @mock.patch("shutil.which")
    def test_refresh_kde_sycoca(self, mock_which, mock_run) -> None:
        mock_which.return_value = "/usr/bin/kbuildsycoca6"
        refresh_kde_sycoca()
        mock_run.assert_called_once_with(["kbuildsycoca6", "--noincremental"], capture_output=True, check=False, timeout=30)

    def test_categorize_web_apps(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = pathlib.Path(tmpdir)
            apps_dir = tmp_path / ".local" / "share" / "applications"
            apps_dir.mkdir(parents=True)

            desktop_file = apps_dir / "brave-test.desktop"
            desktop_file.write_text(
                "[Desktop Entry]\n"
                "Name=Brave WebApp\n"
                "Exec=brave-browser --app=https://example.com\n",
                encoding="utf-8"
            )

            with mock.patch("pathlib.Path.home", return_value=tmp_path):
                with mock.patch.dict(os.environ, {"XDG_DATA_HOME": ""}):
                    categorize_web_apps()

            content = desktop_file.read_text(encoding="utf-8")
            self.assertIn("Categories=X-KythWebApp;", content)


if __name__ == "__main__":
    unittest.main()
