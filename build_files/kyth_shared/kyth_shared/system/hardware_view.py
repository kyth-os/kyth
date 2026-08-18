"""Canonical hardware view — single Evaluation truth for Hub and boot policy.

`hardware_policy.py` is the only place that understands `hardware-profiles.toml`
matching. `services/hardware/*` previously re-parsed `lspci`/`lsusb` for the
same GPU/hybrid decision, so the Hub could disagree with `kyth-hw-setup`.

This module is the single re-export the Hub should import for
“what hardware do we have” — it returns the typed `Evaluation` plus the
persisted applied state, both via the unified ProbeService cache so
`lspci`/`lsusb`/`dmidecode` probes are not re-spawned per page.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kyth_shared.hardware_policy import Evaluation, Inventory, evaluate_system, read_applied_state
from kyth_shared.system.probe import probe_cached

_HARDWARE_VIEW_TTL = 30.0


@dataclass(frozen=True, slots=True)
class HardwareView:
    evaluation: Evaluation
    applied: dict[str, Any]
    has_nvidia: bool
    is_hybrid: bool


def _has_nvidia_from_inventory(inv: Inventory) -> bool:
    return any(dev.vendor == "10de" and dev.class_code.startswith(("03",)) for dev in inv.pci)


def _is_hybrid_from_evaluation(eval_: Evaluation) -> bool:
    caps = set(eval_.capabilities)
    return "gpu.hybrid" in caps or "gpu.offload" in caps


def get_hardware_view() -> HardwareView:
    def _fetch() -> HardwareView:
        evaluation = evaluate_system()
        applied = read_applied_state()
        has_nvidia = _has_nvidia_from_inventory(evaluation.inventory)
        is_hybrid = _is_hybrid_from_evaluation(evaluation)
        return HardwareView(evaluation, applied, has_nvidia, is_hybrid)

    return probe_cached("hardware-view", _HARDWARE_VIEW_TTL, _fetch)


def invalidate_hardware_view() -> None:
    """Invalidate the cached hardware view so the next get_hardware_view() re-probes."""
    from kyth_shared.system.probe import invalidate_probe_caches

    invalidate_probe_caches(["hardware-view", "hardware-summary"])
    # Also clear inventory cache so sysfs is re-scanned
    try:
        from kyth_shared.hardware_policy import invalidate_inventory_cache

        invalidate_inventory_cache()
    except Exception:
        pass
