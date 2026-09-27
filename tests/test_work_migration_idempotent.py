"""Test work_migration_idempotent."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.work_migration_idempotent import *  # noqa: F401,E402 -- star-import is the test: verifies the module imports cleanly


class TestWork_migration_idempotent(unittest.TestCase):
    def test_import(self):
        self.assertTrue(True)
