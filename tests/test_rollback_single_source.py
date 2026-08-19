"""Test rollback_single_source."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.rollback_single_source import *  # noqa: F401,E402 -- star-import is the test: verifies the module imports cleanly


class TestRollback_single_source(unittest.TestCase):
    def test_import(self):
        self.assertTrue(True)
