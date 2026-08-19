"""Hardware quirks catalog — data-driven per-device workarounds.

Each quirk here mirrors one [[quirks]] entry in hardware-profiles.toml.
Keeping them as importable modules makes the match/provenance/actions
triplet testable without parsing TOML, and lets future splits move
quirk-specific validation out of hardware_policy.py (708 LOC monolith).
"""

from __future__ import annotations

from .catalog import QUIRK_MODULES, list_managed_quirks

__all__ = [*QUIRK_MODULES, "QUIRK_MODULES", "list_managed_quirks"]
