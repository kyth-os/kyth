"""Test controller_hotplug."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.controller_hotplug import *  # noqa: F401,E402 -- star-import is the test: verifies the module imports cleanly


class TestController_hotplug(unittest.TestCase):
    def test_import(self):
        self.assertTrue(True)
