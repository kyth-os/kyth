"""Aggregate hardware probes (pure). Qt worker: services.workers.hardware."""
from __future__ import annotations

from dataclasses import dataclass

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
from ..process import command_stdout, probe_cached


def _collect_hardware_probes() -> list[HardwareProbe]:
    def fetch() -> list[HardwareProbe]:
        from ..diagnostics import _system_hub_probe
        pci_text  = command_stdout(["lspci"],  timeout=5)
        usb_text  = command_stdout(["lsusb"],  timeout=5)
        lsmod_text = command_stdout(["lsmod"], timeout=5)
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
    return probe_cached("hardware-probes", 5.0, fetch)


@dataclass(frozen=True)
class HardwareSummaryView:
    """What page_hardware.py's status line and summary card should show
    after a probe run — no Qt, so the decision tree is testable without
    a display."""
    status_text: str
    status_style: str
    summary_card_style: str
    summary_title: str
    summary_body: str


def hardware_summary_view(probes: list[HardwareProbe]) -> HardwareSummaryView:
    levels = {p.status for p in probes}
    errs = [p for p in probes if p.status == "err"]
    warns = [p for p in probes if p.status == "warn"]
    oks = [p for p in probes if p.status == "ok"]

    if "err" in levels:
        return HardwareSummaryView(
            status_text="One or more issues need attention.",
            status_style="status-err",
            summary_card_style="card-accent-err",
            summary_title=f"{len(errs)} hardware issue{'s' if len(errs) != 1 else ''} found",
            summary_body="Start with the issue cards below; each one includes the safest next action when KythOS knows one.",
        )
    if "warn" in levels:
        return HardwareSummaryView(
            status_text="Mostly healthy — a few items worth checking.",
            status_style="status-warn",
            summary_card_style="card-accent-warn",
            summary_title=f"{len(warns)} hardware warning{'s' if len(warns) != 1 else ''}",
            summary_body="The system is usable, but some device, display, driver, or platform checks have recommended follow-up.",
        )
    return HardwareSummaryView(
        status_text="All checks passed.",
        status_style="status-ok",
        summary_card_style="card-accent-ok",
        summary_title=f"All {len(oks)} hardware checks passed",
        summary_body="Graphics, firmware, audio, networking, storage, and platform checks look ready.",
    )


def __getattr__(name: str):
    if name == "HardwareProbeWorker":
        from ..workers.hardware import HardwareProbeWorker
        return HardwareProbeWorker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
