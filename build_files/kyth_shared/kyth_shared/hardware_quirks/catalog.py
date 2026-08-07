"""Declarative quirk catalog — importable, testable view of managed quirks.

Each ``hardware_quirks.*`` module owns one ``QUIRK`` dict that mirrors a
``[[quirks]]`` entry in ``hardware-profiles.toml``. This module enumerates
them in one place so ``validate --fail-expired`` and ``report-quirks`` have
a single source of truth and so ``hardware_policy`` can stay data-only.
"""
from __future__ import annotations

import importlib
from typing import Any

# Keep this tuple as the single enumerator; adding a quirk is adding a module
# and one entry here — reviewable, grep-friendly, and CI-enforceable.
QUIRK_MODULES: tuple[str, ...] = (
    "amdgpu_gaming_memory",
    "intel_i915_media",
    "nvidia_wayland_suspend",
    "mediatek_pcie_wifi_aspm",
    "intel_wifi_association_power",
    "bluetooth_usb_autosuspend",
)

__all__ = [*QUIRK_MODULES, "QUIRK_MODULES", "list_managed_quirks"]


def list_managed_quirks() -> tuple[dict[str, Any], ...]:
    """Return the canonical managed quirks as they appear in per-module files.

    Each entry is the ``QUIRK`` dict from ``hardware_quirks.<module>``.
    The caller owns validation (``_validate_quirk_entry`` in
    ``hardware_policy.py``) — this function is pure enumeration.
    """
    quirks: list[dict[str, Any]] = []
    for name in QUIRK_MODULES:
        mod = importlib.import_module(f"kyth_shared.hardware_quirks.{name}")
        quirk = getattr(mod, "QUIRK", None)
        if not isinstance(quirk, dict) or not quirk.get("id"):
            raise ValueError(f"hardware_quirks.{name}.QUIRK is missing or malformed")
        # Return a shallow copy so callers cannot mutate the module constant.
        quirks.append(dict(quirk))
    return tuple(quirks)
