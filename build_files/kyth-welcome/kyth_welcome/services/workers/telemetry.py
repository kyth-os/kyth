"""Qt worker for fetching telemetry sessions in a background thread."""
from __future__ import annotations

from ...qt import Signal
from ..runtime import TrackedThread
from kyth_shared.telemetry import recent_sessions


class TelemetryWorker(TrackedThread):
    """Query session history from the telemetry database in a background thread."""

    loaded = Signal(list)  # list[SessionRow]

    def __init__(self, limit: int = 15, parent=None):
        super().__init__(parent)
        self.limit = limit

    def run(self) -> None:
        try:
            sessions = recent_sessions(limit=self.limit)
            self.loaded.emit(sessions)
        except Exception:
            self.loaded.emit([])
