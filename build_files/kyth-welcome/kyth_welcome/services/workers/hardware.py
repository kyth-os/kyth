"""Qt worker for aggregate hardware probes."""
from __future__ import annotations

from ...qt import Signal
from ..hardware.collect import _collect_hardware_probes
from ..runtime import TrackedThread


class HardwareProbeWorker(TrackedThread):
    done = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            self.done.emit(_collect_hardware_probes())
        except Exception as exc:
            self.failed.emit(str(exc))
