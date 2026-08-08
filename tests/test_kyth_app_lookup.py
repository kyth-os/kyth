import pathlib
import sys
import unittest
import os
import tempfile
import json

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared import suggest_app


class TestKythAppLookup(unittest.TestCase):
    def test_suggest_app_default_fallback(self):
        # Even if the JSON file is missing, suggest_app should fallback to _DEFAULT_APP_DB
        app_name, suggestion, flatpak_id = suggest_app("winword")
        self.assertEqual(app_name, "Microsoft Word")
        self.assertIn("LibreOffice Writer", suggestion)
        self.assertEqual(flatpak_id, "org.libreoffice.LibreOffice")

    def test_suggest_app_custom_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_json = os.path.join(tmpdir, "apps.json")
            db_data = [
                ["foobar", "Foo Bar App", "Suggesting Foo Bar", "org.foobar.FooBar"]
            ]
            with open(custom_json, "w", encoding="utf-8") as fh:
                json.dump(db_data, fh)

            app_name, suggestion, flatpak_id = suggest_app("foobar-installer", path=custom_json)
            self.assertEqual(app_name, "Foo Bar App")
            self.assertEqual(suggestion, "Suggesting Foo Bar")
            self.assertEqual(flatpak_id, "org.foobar.FooBar")

    def test_exe_handler_lookup_integration(self):
        import importlib.util

        if not any(importlib.util.find_spec(b) for b in ("PySide6", "PyQt6")):
            self.skipTest("PySide6/PyQt6 not available")

        from kyth_shared.desktop.exe_handler import lookup_app_suggestion

        # Test normalisation + lookup
        app_name, _suggestion, flatpak_id = lookup_app_suggestion("Setup_Discord-x64.exe")
        self.assertEqual(app_name, "Discord")
        self.assertEqual(flatpak_id, "com.discordapp.Discord")




if __name__ == "__main__":
    unittest.main()
