"""Aggregate hardware probes and background worker."""
from __future__ import annotations

from ...qt import Signal
from .types import HardwareProbe
from .nvidia import _gpu_probe
from .io import (
    _audio_probe,
    _connectivity_probe,
    _controller_probe,
    _displaylink_probe,
    _firmware_probe,
    _peripheral_probe,
)
from .display import _display_probe
from .system import (
    _cpu_probe,
    _memory_probe,
    _platform_probe,
    _storage_probe,
    _thermal_probe,
)
from .codec import _codec_probe
from ..process import _command_stdout, _probe_cached
from ..runtime import TrackedThread


class HardwareProbeWorker(TrackedThread):
    done = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            self.done.emit(_collect_hardware_probes())
        except Exception as exc:
            self.failed.emit(str(exc))


def _collect_hardware_probes() -> list[HardwareProbe]:
    def fetch() -> list[HardwareProbe]:
        from ..diagnostics import _system_hub_probe
        pci_text  = _command_stdout(["lspci"],  timeout=5)
        usb_text  = _command_stdout(["lsusb"],  timeout=5)
        lsmod_text = _command_stdout(["lsmod"], timeout=5)
        return [
            # Gaming-critical first
            _gpu_probe(pci_text, lsmod_text),
            _cpu_probe(),
            _display_probe(),
            _memory_probe(),
            # Input devices
            _controller_probe(usb_text, lsmod_text),
            _peripheral_probe(usb_text),
            _displaylink_probe(usb_text, lsmod_text),
            # System health
            _audio_probe(),
            _thermal_probe(),
            _connectivity_probe(pci_text, usb_text),
            _codec_probe(),
            _firmware_probe(),
            _storage_probe(),
            _platform_probe(),
            _system_hub_probe(),
        ]
    return _probe_cached("hardware-probes", 5.0, fetch)
