"""Privilege helpers — extracted from system.py 383 monolith (step 1)."""
from __future__ import annotations

from .system import _as_root, _require_no_symlink, _safe_umount, require_root

__all__ = ["_as_root", "_require_no_symlink", "_safe_umount", "require_root"]
