"""HubState control-plane helpers used by Update/Repair pages."""
from __future__ import annotations

import pathlib
import sys
import types
import unittest


def _install_qt_stubs() -> None:
    class _Signal:
        def __init__(self, *args, **kwargs):
            pass

        def __get__(self, obj, objtype=None):
            return self

        def emit(self, *args, **kwargs):
            pass

        def connect(self, *args, **kwargs):
            pass

    # hub_state imports PySide6 directly before falling back — stub both.
    for pkg in ("PySide6", "PySide6.QtCore", "PyQt6", "PyQt6.QtCore"):
        sys.modules[pkg] = types.ModuleType(pkg)
    sys.modules["PySide6.QtCore"].QObject = object
    sys.modules["PySide6.QtCore"].Signal = _Signal
    sys.modules["PyQt6.QtCore"].QObject = object
    sys.modules["PyQt6.QtCore"].pyqtSignal = _Signal


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "kyth-welcome"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))
_install_qt_stubs()

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
