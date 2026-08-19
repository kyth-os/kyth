"""Test perf_transaction."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.perf_transaction import *  # noqa: F401,E402 -- star-import is the test: verifies the module imports cleanly


class TestPerf_transaction(unittest.TestCase):
    def test_import(self):
        self.assertTrue(True)
