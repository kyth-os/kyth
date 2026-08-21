"""HubState control-plane helpers used by Update/Repair pages."""
from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "kyth-welcome"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

# hub_state falls back to a pure-Python store when Qt bindings are absent.
# Do not stub PySide6 into sys.modules — that breaks later find_spec() checks
# in the full unittest discover suite (ValueError: PySide6.__spec__ is None).
from kyth_welcome.services.hub_state import HubState  # noqa: E402


class HubStateTests(unittest.TestCase):
    def test_update_and_rollback_roundtrip(self):
        state = HubState()
        state.set_update_status("staged", "reboot")
        self.assertEqual(state.get_update_status()["status"], "staged")
        self.assertEqual(state.get_update_status()["detail"], "reboot")
        state.set_rollback_available(True)
        self.assertTrue(state.is_rollback_available())
        state.set_rollback_available(False)
        self.assertFalse(state.is_rollback_available())

    def test_repair_plan_clear(self):
        state = HubState()
        state.set_repair_plan({"summary": "x"})
        self.assertEqual(state.get_repair_plan()["summary"], "x")
        state.set_repair_plan(None)
        self.assertIsNone(state.get_repair_plan())


if __name__ == "__main__":
    unittest.main()
