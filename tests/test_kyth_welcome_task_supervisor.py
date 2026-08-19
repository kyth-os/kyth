"""TaskSupervisor.finish_owner_task connect-before-check race regression.

Runs offscreen (QT_QPA_PLATFORM=offscreen); skips gracefully without PySide6
(same pattern as test_kyth_welcome_hub_smoke.py).
"""
from __future__ import annotations

import os
import pathlib
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

try:
    from PySide6.QtCore import QCoreApplication, QThread
except ImportError:
    raise unittest.SkipTest("PySide6 required for TaskSupervisor race regression") from None


class _InstantThread(QThread):
    def run(self) -> None:
        pass  # finishes essentially immediately


class TaskSupervisorFinishRaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from kyth_welcome.services.runtime import TaskSupervisor
        except ImportError as exc:
            raise unittest.SkipTest(f"Qt not available (mocked): {exc}") from exc
        cls.TaskSupervisor = TaskSupervisor
        cls._app = QCoreApplication.instance() or QCoreApplication(sys.argv)

    def test_finish_owner_task_does_not_leak_when_isFinished_races_the_signal(self):
        # Reproduces the exact TOCTOU window the fix closes. isFinished()'s
        # side effect stands in for real concurrent timing: it blocks until
        # the thread has genuinely finished and pumps the event loop so its
        # `finished` signal is fully delivered to whoever is connected AT
        # THAT MOMENT — before returning a (possibly stale) answer, exactly
        # like a real check whose result can already be out of date by the
        # time the caller acts on it.
        #
        # Fixed code connects _cleanup to `finished` BEFORE calling
        # isFinished(), so it's already listening when the side effect's
        # wait()+processEvents() flushes the real completion — the signal
        # is delivered normally regardless of what isFinished() goes on to
        # report. Pre-fix code called isFinished() FIRST: the side effect's
        # completion+flush happens with nobody connected yet, so the
        # deferred connect() that follows registers too late and the
        # already-delivered signal is gone for good — owner.worker and the
        # _TaskRecord leak forever.
        thread = _InstantThread()
        owner = type("Owner", (), {})()
        owner.worker = thread
        thread.start()

        supervisor = self.TaskSupervisor()
        supervisor.attach(thread, owner, "worker")

        def _isfinished_side_effect():
            thread.wait()
            for _ in range(5):
                self._app.processEvents()
            return False

        with patch.object(thread, "isFinished", side_effect=_isfinished_side_effect):
            supervisor.finish_owner_task(owner, "worker")
            for _ in range(5):
                self._app.processEvents()

        self.assertIsNone(owner.worker)
        self.assertNotIn(thread, supervisor._records)


if __name__ == "__main__":
    unittest.main()
