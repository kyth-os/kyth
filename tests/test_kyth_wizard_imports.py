"""Regression coverage for the first-run wizard's split module imports."""
from __future__ import annotations

import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WIZARD_DIR = (
    ROOT
    / "build_files"
    / "kyth-welcome"
    / "kyth_welcome"
    / "wizard"
)


class WizardImportTests(unittest.TestCase):
    def test_wizard_runtime_helpers_are_imported(self):
        """Every helper used after the wizard refactor must be in scope."""
        required = {
            "window.py": {"QIcon", "_divider", "_save_profile"},
            "steps_apps.py": {"QFrame", "QScrollArea", "QSizePolicy", "Qt"},
            "steps_gaming.py": {"_divider"},
            "steps_welcome.py": {"_command_stdout", "_divider"},
        }
        for filename, expected in required.items():
            with self.subTest(filename=filename):
                tree = ast.parse((WIZARD_DIR / filename).read_text(encoding="utf-8"))
                imported = {
                    alias.asname or alias.name.split(".")[0]
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                    for alias in node.names
                }
                self.assertTrue(
                    expected.issubset(imported),
                    f"{filename} is missing a runtime import",
                )


if __name__ == "__main__":
    unittest.main()
