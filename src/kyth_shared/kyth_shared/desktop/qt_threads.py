"""Tracked QThread helpers for session daemons outside System Hub.

Hub pages use ``kyth_welcome.services.runtime.TrackedThread``. Standalone Qt
tools (update notifier, exe handler) must still join workers on quit — destroying
a running QThread aborts the process.
"""
from __future__ import annotations

import atexit
import logging

from kyth_shared.qt import QThread

_logger = logging.getLogger(__name__)

_LIVE: list[QThread] = []


class TrackedThread(QThread):
    """QThread that stays referenced while alive and is joined at process exit."""

    BLOCKS_CLOSE = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _LIVE.append(self)
        self.finished.connect(self._drop)

    def _drop(self) -> None:
        try:
            _LIVE.remove(self)
        except ValueError:
            pass


def running_threads() -> list[QThread]:
    return [thread for thread in _LIVE if thread.isRunning()]


def shutdown_threads(timeout_ms: int = 15000) -> None:
    """Request interruption and join every tracked thread."""
    alive = list(_LIVE)
    for thread in alive:
        try:
            thread.requestInterruption()
        except RuntimeError:
            pass
    for thread in alive:
        try:
            if thread.isRunning():
                thread.wait(timeout_ms)
        except RuntimeError:
            _logger.debug("shutdown_threads: wait failed", exc_info=True)


atexit.register(shutdown_threads)
