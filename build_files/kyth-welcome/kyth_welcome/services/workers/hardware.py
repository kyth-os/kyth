"""Qt workers for hardware and controller detection."""
from __future__ import annotations

from ...qt import Signal
from ..hardware import _detect_controllers
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


class ControllerProbeWorker(TrackedThread):
    result = Signal(dict)

    def run(self) -> None:
        try:
            self.result.emit(_detect_controllers())
        except (OSError, RuntimeError):
            self.result.emit({})
