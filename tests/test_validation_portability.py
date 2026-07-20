"""Validate that the test suite remains importable without optional Qt bindings."""
from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ValidationPortabilityTests(unittest.TestCase):
    def test_test_modules_import_when_qt_is_unavailable(self):
        script = r"""
import importlib.abc
import importlib.util
import pathlib
import runpy
import unittest

real_find_spec = importlib.util.find_spec

def find_spec(name, *args, **kwargs):
    if name in {"PySide6", "PyQt6"}:
        return None
    return real_find_spec(name, *args, **kwargs)

class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "PySide6" or fullname.startswith("PySide6."):
            raise ModuleNotFoundError(fullname)
        if fullname == "PyQt6" or fullname.startswith("PyQt6."):
            raise ModuleNotFoundError(fullname)
        return None

importlib.util.find_spec = find_spec
sys.meta_path.insert(0, BlockQt())
for test_file in sorted(pathlib.Path("tests").glob("test_*.py")):
    try:
        runpy.run_path(test_file, run_name=f"validation_{test_file.stem}")
    except unittest.SkipTest:
        pass
"""
        result = subprocess.run(
            [sys.executable, "-c", "import sys\n" + script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
