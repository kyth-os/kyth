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
        # Import the build_files/kyth-exe-handler module dynamically. It has
        # no .py suffix, so spec_from_file_location needs an explicit loader
        # to recognize it as source rather than failing to infer one.
        import importlib.util
        from importlib.machinery import SourceFileLoader
        from unittest.mock import MagicMock

        # Stub out kyth_shared.qt so it doesn't crash without PyQt6/PySide6
        sys.modules["kyth_shared.qt"] = MagicMock()

        handler_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "build_files", "kyth-exe-handler")
        loader = SourceFileLoader("kyth_exe_handler", handler_path)
        spec = importlib.util.spec_from_file_location("kyth_exe_handler", handler_path, loader=loader)
        kyth_exe_handler = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(kyth_exe_handler)

        # Test normalisation + lookup
        app_name, _suggestion, flatpak_id = kyth_exe_handler._lookup("Setup_Discord-x64.exe")
        self.assertEqual(app_name, "Discord")
        self.assertEqual(flatpak_id, "com.discordapp.Discord")


if __name__ == "__main__":
    unittest.main()
