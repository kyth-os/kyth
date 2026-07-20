import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services.windows_migration import extras  # noqa: E402


class WindowsMigrationExtrasTests(unittest.TestCase):
    def test_dir_contains_saves_detects_save_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            save_file = os.path.join(tmp, "game.sav")
            with open(save_file, "w") as fh:
                fh.write("dummy save")
            self.assertTrue(extras.dir_contains_saves(tmp))

    def test_image_extension_sniffs_png_and_jpg(self):
        with tempfile.TemporaryDirectory() as tmp:
            png_file = os.path.join(tmp, "test.png")
            with open(png_file, "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n")
            self.assertEqual(extras.image_extension(png_file), ".png")

            jpg_file = os.path.join(tmp, "test.jpg")
            with open(jpg_file, "wb") as fh:
                fh.write(b"\xff\xd8\xff\xe0")
            self.assertEqual(extras.image_extension(jpg_file), ".jpg")

    def test_parse_rdp_file_extracts_host_and_username(self):
        with tempfile.TemporaryDirectory() as tmp:
            rdp_path = os.path.join(tmp, "server.rdp")
            content = "full address:s:192.168.1.100:3389\nusername:s:Administrator\n"
            with open(rdp_path, "w", encoding="utf-8") as fh:
                fh.write(content)

            parsed = extras.parse_rdp_file(rdp_path)
            self.assertIsNotNone(parsed)
            self.assertEqual(parsed["host"], "192.168.1.100:3389")
            self.assertEqual(parsed["username"], "Administrator")

    def test_export_sticky_notes_writes_text_files(self):
        sticky_data = [
            {
                "user": "Alice",
                "notes": ["First line of note\\id=12345678-1234-1234-1234-123456789012\nSecond line"],
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            with patch("kyth_welcome.services.windows_migration.extras.windows_folder_dest", return_value=tmp):
                count, base = extras.export_sticky_notes(sticky_data)

            self.assertEqual(count, 1)
            self.assertTrue(os.path.exists(base))

    def test_import_rdp_bookmarks_creates_xbel(self):
        conns = [{"name": "Server1", "host": "10.0.0.1", "username": "admin"}]
        with tempfile.TemporaryDirectory() as tmp:
            xbel_path = os.path.join(tmp, "bookmarks.xbel")
            with patch("os.path.expanduser", return_value=xbel_path):
                added, dupes = extras.import_rdp_bookmarks(conns)

            self.assertEqual(added, 1)
            self.assertEqual(dupes, 0)
            self.assertTrue(os.path.exists(xbel_path))


if __name__ == "__main__":
    unittest.main()
