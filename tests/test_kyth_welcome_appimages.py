import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services import appimages  # noqa: E402


class AppImagesServiceTests(unittest.TestCase):
    def setUp(self):
        self._home_dir = tempfile.TemporaryDirectory()
        self.home = self._home_dir.name

    def tearDown(self):
        self._home_dir.cleanup()

    def _touch(self, *parts: str) -> str:
        path = Path(self.home, *parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return str(path)

    def test_is_user_appimage_path_requires_home_and_extension(self):
        appimage = self._touch("Applications", "Obsidian.AppImage")
        self.assertTrue(appimages.is_user_appimage_path(appimage, self.home))
        self.assertFalse(appimages.is_user_appimage_path("", self.home))

    def test_is_user_appimage_path_rejects_paths_outside_home(self):
        with tempfile.TemporaryDirectory() as other_dir:
            outside = Path(other_dir, "Tool.AppImage")
            outside.write_text("", encoding="utf-8")
            self.assertFalse(appimages.is_user_appimage_path(str(outside), self.home))

    def test_is_user_appimage_path_rejects_non_appimage_extension(self):
        script = self._touch("Applications", "run.sh")
        self.assertFalse(appimages.is_user_appimage_path(script, self.home))

    def test_desktop_entry_from_exec_line_resolves_appimage(self):
        appimage = self._touch("Applications", "Obsidian.AppImage")
        desktop_text = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name=Obsidian\n"
            f"Exec={appimage} --no-sandbox\n"
            "Icon=obsidian\n"
        )
        entry = appimages.appimage_entry_from_desktop_text(
            desktop_text, "/home/user/.local/share/applications/obsidian.desktop", self.home
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry["name"], "Obsidian")
        self.assertEqual(entry["path"], appimage)
        self.assertEqual(entry["kind"], "appimage")

    def test_desktop_entry_without_appimage_exec_returns_none(self):
        desktop_text = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Firefox\n"
            "Exec=/usr/bin/firefox %u\n"
        )
        entry = appimages.appimage_entry_from_desktop_text(desktop_text, "/x/firefox.desktop", self.home)
        self.assertIsNone(entry)

    def test_desktop_entry_missing_section_returns_none(self):
        entry = appimages.appimage_entry_from_desktop_text("not a desktop file", "/x/bad.desktop", self.home)
        self.assertIsNone(entry)

    def test_desktop_entry_falls_back_to_basename_when_no_name(self):
        appimage = self._touch("Applications", "Tool.AppImage")
        desktop_text = f"[Desktop Entry]\nExec={appimage}\n"
        entry = appimages.appimage_entry_from_desktop_text(desktop_text, "/x/tool.desktop", self.home)
        self.assertEqual(entry["name"], "Tool.AppImage")

    def test_uninstall_app_detail_formats_appimage_and_flatpak(self):
        appimage = {"kind": "appimage", "path": "/home/u/Tool.AppImage", "desktop_path": ""}
        self.assertEqual(appimages.uninstall_app_detail(appimage), "/home/u/Tool.AppImage · AppImage")

        with_launcher = {**appimage, "desktop_path": "/x.desktop"}
        self.assertIn("· launcher", appimages.uninstall_app_detail(with_launcher))

        flatpak = {
            "kind": "flatpak", "app_id": "org.mozilla.firefox",
            "installation": "user", "origin": "flathub",
        }
        self.assertEqual(
            appimages.uninstall_app_detail(flatpak), "org.mozilla.firefox · user install · flathub"
        )

    def test_safe_home_targets_keeps_only_paths_under_home(self):
        inside = self._touch("Applications", "Tool.AppImage")
        result = appimages.safe_home_targets([inside, "/etc/passwd", "/root/.bashrc"], self.home)
        self.assertEqual(result, [inside])

    def test_flatpak_uninstall_command_adds_scope_flag(self):
        self.assertIn("--user", appimages.flatpak_uninstall_command("org.app.Id", "user"))
        self.assertIn("--system", appimages.flatpak_uninstall_command("org.app.Id", "system"))
        cmd = appimages.flatpak_uninstall_command("org.app.Id", "user file")
        self.assertNotIn("--user", cmd)
        self.assertNotIn("--system", cmd)
        self.assertEqual(cmd[-1], "org.app.Id")


if __name__ == "__main__":
    unittest.main()
