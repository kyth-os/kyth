"""Pure disk parsing helpers — extracted from kyth_installer.disk for fuzzing.

These functions have no subprocess or filesystem side-effects beyond
`os.path.realpath` for device normalization, making them suitable for
unit and fuzz testing without mocking `run_command`.
"""
from __future__ import annotations

import os
import re

_SAFE_DEVICE_PATH_RE = re.compile(r"^/dev/[A-Za-z0-9._/+:-]+$")


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _normal_device_path(name: str | None) -> str | None:
    if not name:
        return None
    name = str(name).strip()
    if not name:
        return None
    if not name.startswith("/dev/"):
        name = f"/dev/{name}"
    real = os.path.realpath(name)
    if not real.startswith("/dev/"):
        return None
    if not _SAFE_DEVICE_PATH_RE.fullmatch(real):
        return None
    return real
