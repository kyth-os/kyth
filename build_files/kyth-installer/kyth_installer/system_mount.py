"""Mount helpers — extracted from system.py monolith (step 1)."""
from __future__ import annotations

from .system import unmount_target_disk, _settle

__all__ = ["unmount_target_disk", "_settle"]
