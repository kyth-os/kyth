"""Regression checks for names used only by deferred UI callbacks."""
from __future__ import annotations

import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "build_files" / "kyth-welcome" / "kyth_welcome"


class RefactorRuntimeImportTests(unittest.TestCase):
    def test_deferred_callback_dependencies_are_imported(self):
        required = {
            "page_hardware.py": {"_command_stdout"},
            "page_repair_quick.py": {"shlex"},
            "page_welcome.py": {"time"},
        }
        for relative_path, expected in required.items():
            with self.subTest(path=relative_path):
                tree = ast.parse((PACKAGE / relative_path).read_text(encoding="utf-8"))
                imported = {
                    alias.asname or alias.name.split(".")[0]
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                    for alias in node.names
                }
                self.assertTrue(expected.issubset(imported))


if __name__ == "__main__":
    unittest.main()
