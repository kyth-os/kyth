"""Test work_migration_idempotent."""
import unittest
from kyth_shared.work_migration_idempotent import *  # noqa: F401 -- star-import is the test: verifies the module imports cleanly
class TestWork_migration_idempotent (unittest.TestCase):
    def test_import(self):
        self.assertTrue(True)
