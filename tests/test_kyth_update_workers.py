import importlib
import pathlib
import sys
import types
import unittest
from unittest.mock import Mock, patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))


def _install_qt_stub() -> None:
    class _Signal:
        def __init__(self, *_args):
            pass

        def connect(self, *_args):
            pass

        def emit(self, *_args):
            pass

    class _Thread:
        def __init__(self, *_args, **_kwargs):
            self.finished = _Signal()

        def isRunning(self):
            return False

    qt = types.ModuleType("kyth_welcome.qt")
    qt.QThread = _Thread
    qt.Signal = _Signal
    sys.modules["kyth_welcome.qt"] = qt


_install_qt_stub()
updates = importlib.import_module("kyth_welcome.services.workers.updates")


class UpdateCheckWorkerTests(unittest.TestCase):
    def _worker(self, *, use_cached_snapshot=True):
        worker = updates.UpdateCheckWorker(use_cached_snapshot=use_cached_snapshot)
        worker.result = Mock()
        return worker

    def test_background_check_uses_valid_snapshot(self):
        snapshot = Mock(system_state="uptodate")
        worker = self._worker()

        with (
            patch.object(updates, "read_update_snapshot", return_value=snapshot) as read_snapshot,
            patch.object(updates, "check_registry_update") as registry_check,
        ):
            worker.run()

        read_snapshot.assert_called_once_with(max_age=300)
        registry_check.assert_not_called()
        emitted = worker.result.emit.call_args.args[0]
        self.assertEqual((emitted.probe, emitted.state, emitted.value), ("system", "ok", "uptodate"))

    def test_forced_check_bypasses_valid_snapshot(self):
        result = Mock(state="available", detail="new", manifest_raw=b"manifest")
        worker = self._worker(use_cached_snapshot=False)

        with (
            patch.object(updates, "read_update_snapshot") as read_snapshot,
            patch.object(updates, "bootc_status_data", return_value={"status": {}}),
            patch.object(updates, "current_branch", return_value="testing"),
            patch.object(updates, "check_registry_update", return_value=result) as registry_check,
        ):
            worker.run()

        read_snapshot.assert_not_called()
        registry_check.assert_called_once()
        emitted = worker.result.emit.call_args.args[0]
        self.assertEqual(
            (emitted.probe, emitted.state, emitted.value, emitted.detail, emitted.manifest_raw),
            ("system", "ok", "available", "new", "manifest"),
        )

    def test_unknown_snapshot_falls_back_to_registry(self):
        snapshot = Mock(system_state="unknown")
        result = Mock(state="error", detail="timed out", manifest_raw=b"")
        worker = self._worker()

        with (
            patch.object(updates, "read_update_snapshot", return_value=snapshot),
            patch.object(updates, "bootc_status_data", return_value={}),
            patch.object(updates, "current_branch", return_value=None),
            patch.object(updates, "check_registry_update", return_value=result),
        ):
            worker.run()

        emitted = worker.result.emit.call_args.args[0]
        self.assertEqual(
            (emitted.probe, emitted.state, emitted.detail),
            ("system", "error", "timed out"),
        )

    def test_unexpected_failure_still_emits_completion_result(self):
        worker = self._worker(use_cached_snapshot=False)
        with patch.object(updates, "bootc_status_data", side_effect=RuntimeError("broken probe")):
            worker.run()

        emitted = worker.result.emit.call_args.args[0]
        self.assertEqual(
            (emitted.probe, emitted.state, emitted.detail),
            ("system", "error", "broken probe"),
        )


if __name__ == "__main__":
    unittest.main()
