"""Pure Windows migration helpers (no Qt)."""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services.windows_migration.bookmarks import (  # noqa: E402
    read_chromium_bookmarks,
    write_bookmarks_html,
)
from kyth_welcome.services.windows_migration.extras import (  # noqa: E402
    dir_contains_saves,
    image_extension,
    parse_rdp_file,
)
from kyth_welcome.services.windows_migration.hardware_sanity import (  # noqa: E402
    strip_ansi,
    hw_display_row,
)
from kyth_welcome.services.phone_link import (  # noqa: E402
    load_dynamic_lock_config,
    save_dynamic_lock_config,
)


class BookmarkTests(unittest.TestCase):
    def test_read_chromium_bookmarks(self):
        data = {
            "roots": {
                "bookmark_bar": {
                    "children": [
                        {"type": "url", "name": "Kyth", "url": "https://example.com/a"},
                        {
                            "type": "folder",
                            "children": [
                                {"type": "url", "name": "Dup", "url": "https://example.com/a"},
                                {"type": "url", "name": "Other", "url": "https://example.com/b"},
                            ],
                        },
                    ]
                }
            }
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(data, fh)
            path = fh.name
        try:
            entries = read_chromium_bookmarks(path)
        finally:
            pathlib.Path(path).unlink(missing_ok=True)
        self.assertEqual(
            entries,
            [("Kyth", "https://example.com/a"), ("Other", "https://example.com/b")],
        )

    def test_write_bookmarks_html(self):
        sources = [
            {
                "browser": "Chrome",
                "user": "Alice",
                "entries": [("Home", "https://example.com/")],
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            dest = pathlib.Path(tmp) / "bookmarks.html"
            total = write_bookmarks_html(sources, str(dest))
            self.assertEqual(total, 1)
            text = dest.read_text(encoding="utf-8")
            self.assertIn("NETSCAPE-Bookmark-file-1", text)
            self.assertIn("https://example.com/", text)
            self.assertIn("Chrome", text)


class ExtrasTests(unittest.TestCase):
    def test_dir_contains_saves_by_dirname(self):
        with tempfile.TemporaryDirectory() as tmp:
            saves = pathlib.Path(tmp) / "Saves"
            saves.mkdir()
            (saves / "slot1.dat").write_text("x")
            self.assertTrue(dir_contains_saves(tmp))

    def test_dir_contains_saves_by_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "progress.sav").write_bytes(b"x")
            self.assertTrue(dir_contains_saves(tmp))

    def test_dir_contains_saves_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "readme.txt").write_text("hi")
            self.assertFalse(dir_contains_saves(tmp))

    def test_image_extension_sniff(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = pathlib.Path(tmp) / "wall"
            png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 8)
            self.assertEqual(image_extension(str(png)), ".png")
            bmp = pathlib.Path(tmp) / "wall2"
            bmp.write_bytes(b"BM" + b"\0" * 10)
            self.assertEqual(image_extension(str(bmp)), ".bmp")

    def test_parse_rdp_file_utf16(self):
        content = "full address:s:work.example.com\nusername:s:alice\n"
        with tempfile.NamedTemporaryFile("wb", suffix=".rdp", delete=False) as fh:
            fh.write(b"\xff\xfe" + content.encode("utf-16-le"))
            path = fh.name
        try:
            parsed = parse_rdp_file(path)
        finally:
            pathlib.Path(path).unlink(missing_ok=True)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["host"], "work.example.com")
        self.assertEqual(parsed["username"], "alice")
        self.assertEqual(parsed["name"], pathlib.Path(path).stem)


class HardwareSanityTests(unittest.TestCase):
    def test_strip_ansi(self):
        self.assertEqual(strip_ansi("\x1b[32mOK\x1b[0m"), "OK")

    def test_strip_ansi_non_color_csi_sequences(self):
        # Cursor-movement/erase CSI codes end in letters other than 'm'
        # (e.g. 'H', 'K'); a color-only regex would leave these behind.
        self.assertEqual(strip_ansi("\x1b[2K\x1b[1GHDR: enabled"), "HDR: enabled")

    def test_hw_display_row_hdr_vrr(self):
        sample = "Output: HDMI-1\nHDR: enabled\nVRR: automatic\n"
        with patch(
            "kyth_welcome.services.windows_migration.hardware_sanity.command_stdout",
            return_value=sample,
        ):
            row = hw_display_row()
        self.assertIsNotNone(row)
        assert row is not None
        status, title, text = row
        self.assertEqual(status, "ok")
        self.assertEqual(title, "Display")
        self.assertIn("HDR", text)
        self.assertIn("variable refresh", text.lower())


class PhoneLinkConfigTests(unittest.TestCase):
    def test_dynamic_lock_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = pathlib.Path(tmp) / "kyth-dynamic-lock.json"
            with patch(
                "kyth_welcome.services.phone_link._DYNAMIC_LOCK_CONFIG",
                str(cfg_path),
            ):
                save_dynamic_lock_config({"enabled": True, "device_id": "abc"})
                loaded = load_dynamic_lock_config()
            self.assertEqual(loaded.get("enabled"), True)
            self.assertEqual(loaded.get("device_id"), "abc")


if __name__ == "__main__":
    unittest.main()
