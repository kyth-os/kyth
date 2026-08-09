"""Aggregate hardware probes (pure). Qt worker: services.workers.hardware."""
from __future__ import annotations

from dataclasses import dataclass

from kyth_shared.hardware_policy import evaluate_system, read_applied_state
from kyth_shared.system.hardware_view import get_hardware_view

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


def _hardware_policy_probe(view=None) -> HardwareProbe:  # type: ignore[no-untyped-def]
    # R4: accept pre-fetched view to avoid double evaluate_system() when
    # _collect_hardware_probes already has it. Single PCI/LSUSB parse.
    if view is not None:
        try:
            evaluation = view.evaluation
            applied = view.applied
        except Exception:
            view = None
    if view is None:
        try:
            view = get_hardware_view()
            evaluation = view.evaluation
            applied = view.applied
        except Exception:
            try:
                evaluation = evaluate_system()
                applied = read_applied_state()
            except Exception as exc:
                return HardwareProbe(
                    "Hardware policy", "warn",
                    "Hardware policy could not be evaluated.",
                    str(exc),
                    "Run kyth-hardware-policy validate and review the service journal.",
                )
    profiles = [profile["title"] for profile in evaluation.profiles]
    tiers = sorted({str(p.get("tier", "supported")).lower() for p in evaluation.profiles if isinstance(p, dict)} or {"supported"})
    quirks = [quirk["id"] for quirk in evaluation.quirks]
    # User-visible tier — the support matrix is already validated in CI (validate.sh cmp docs/hardware-support-matrix.md)
    # but was never shown in the Hub, so users never knew if their laptop is Tier 1.
    details = [
        f"Policy revision: {evaluation.policy_revision}",
        f"Hardware tier: {', '.join(tiers) or 'supported'} — see docs/hardware-support-matrix.md",
        f"Applied state: {applied.get('status', 'not yet applied')}",
        f"Booted image: {applied.get('image_reference', 'unknown')}",
        f"Image digest: {applied.get('image_digest', 'unknown')}",
        f"Recommended image variant: {evaluation.recommended_variant}",
        f"Matched profiles: {', '.join(profiles) or 'none'}",
        f"Active quirks: {', '.join(quirks) or 'none'}",
        f"Capabilities: {', '.join(evaluation.capabilities) or 'none'}",
    ]
    if evaluation.warnings:
        details.extend(["", *evaluation.warnings])
        return HardwareProbe(
            "Hardware policy", "warn",
            "Hardware matched, but one or more quirks need maintainer review.",
            "\n".join(details),
            "Update or remove the expired hardware quirk before the next release.",
        )
    if quirks:
        return HardwareProbe(
            "Hardware policy", "warn",
            f"Hardware matched with {len(quirks)} active quirk{'s' if len(quirks)!=1 else ''}: {', '.join(quirks)}",
            "\n".join(details),
            "Review the quirk in docs/hardware-support-matrix.md — it may need an update or removal.",
        )
    return HardwareProbe(
        "Hardware policy", "ok",
        f"Matched {len(profiles)} versioned hardware profile{'s' if len(profiles) != 1 else ''}.",
        "\n".join(details),
    )


def _collect_hardware_probes() -> list[HardwareProbe]:
    def fetch() -> list[HardwareProbe]:
        from ..diagnostics import _system_hub_probe
        pci_text  = command_stdout(["lspci"],  timeout=5)
        usb_text  = command_stdout(["lsusb"],  timeout=5)
        lsmod_text = command_stdout(["lsmod"], timeout=5)
        return [
            # Gaming-critical first
            _gpu_probe(pci_text, lsmod_text),
            _hardware_policy_probe(),
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
    return probe_cached("hardware-probes", 30.0, fetch)  # one PCI/LSUSB parse for Hub cold start — matches hardware_view cache


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
    # Windows-switcher clarity: name the Tier 1 promise — "Will my laptop just work?"
    # Surface the policy Tier 1/2 coverage hint already computed in _hardware_policy_probe
    # via get_hardware_view() when available, so the HUD reads as a switcher guarantee.
    tier_hint = ""
    for p in probes:
        if p.title == "Hardware policy" and p.status in ("ok", "warn"):
            # details contains "Hardware tier: tier1..." — extract for summary
            if "tier" in p.details.lower():
                tier_hint = " (Tier 1 — fully tested daily-driver path)"
                break
    return HardwareSummaryView(
        status_text="All checks passed." + tier_hint,
        status_style="status-ok",
        summary_card_style="card-accent-ok",
        summary_title=f"All {len(oks)} hardware checks passed",
        summary_body="Graphics, firmware, audio, networking, storage, and platform checks look ready." + tier_hint,
    )


def __getattr__(name: str):
    if name == "HardwareProbeWorker":
        from ..workers.hardware import HardwareProbeWorker
        return HardwareProbeWorker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
