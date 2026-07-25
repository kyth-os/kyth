import unittest
import tempfile
import os
import json
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.apps import load_app_db, suggest_app, _DEFAULT_APP_DB


class TestKythSharedApps(unittest.TestCase):
    def test_load_app_db_default(self):
        # Non-existent path returns defaults
        db = load_app_db("/nonexistent/file.json")
        self.assertEqual(db, _DEFAULT_APP_DB)

    def test_load_app_db_valid_json(self):
        # Valid JSON path
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        try:
            custom_db = [
                ["pattern1", "App Name 1", "Suggestion 1", "Flatpak 1"],
                ["pattern2", "App Name 2", "Suggestion 2", None],
            ]
            with open(temp_file.name, "w", encoding="utf-8") as fh:
                json.dump(custom_db, fh)
            
            db = load_app_db(temp_file.name)
            self.assertEqual(len(db), 2)
            self.assertEqual(db[0], ("pattern1", "App Name 1", "Suggestion 1", "Flatpak 1"))
            self.assertEqual(db[1], ("pattern2", "App Name 2", "Suggestion 2", None))
        finally:
            os.remove(temp_file.name)

    def test_load_app_db_invalid_json(self):
        # Corrupted/invalid JSON file returns default
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        try:
            with open(temp_file.name, "w", encoding="utf-8") as fh:
                fh.write("{invalid: json}")
            
            db = load_app_db(temp_file.name)
            self.assertEqual(db, _DEFAULT_APP_DB)
        finally:
            os.remove(temp_file.name)

    def test_suggest_app(self):
        # Test direct lookup
        app_name, suggestion, flathub_id = suggest_app("word")
        self.assertEqual(app_name, "Microsoft Word")
        self.assertEqual(suggestion, "Use LibreOffice Writer — fully compatible with .docx files.")
        self.assertEqual(flathub_id, "org.libreoffice.LibreOffice")

        app_name, suggestion, flathub_id = suggest_app("nonexistent-app-stem-here")
        self.assertIsNone(app_name)
        self.assertIsNone(flathub_id)


if __name__ == "__main__":
    unittest.main()
