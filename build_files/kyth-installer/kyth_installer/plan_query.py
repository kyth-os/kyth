"""Plan query — read-only discovery helpers for the review/install pages.

Extracted from plan.py 678 monolith (step 4). No writes.
"""
from __future__ import annotations

from .plan import (  # noqa: F401
    _get_manual_mounts,
    _has_bios_boot_partition,
    _is_gpt_disk,
    _probe_storage,
    _required_guided_space,
    disk_hold,
    find_bootcurrent_esp,
    suggest_windows_resize_target,
)

__all__ = [
    "_get_manual_mounts",
    "_has_bios_boot_partition",
    "_is_gpt_disk",
    "_probe_storage",
    "_required_guided_space",
    "disk_hold",
    "find_bootcurrent_esp",
    "suggest_windows_resize_target",
]
