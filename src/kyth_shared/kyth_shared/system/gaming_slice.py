"""Per-game cgroup slice helper — scoped gaming boost without global sysctl aggression.

Used by kyth-game-boost and Hub's gaming launch path. Validates slice exists
and falls back to direct exec if systemd-run unavailable (VM, container).
Mirrors the pattern from kyth-game-boost: systemd-run --slice=gaming.slice --scope
so placement survives pressure-vessel/bwrap.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def gaming_slice_command(argv: list[str], use_user: bool | None = None) -> list[str]:
    """Return systemd-run wrapper for argv, or argv unchanged if not available."""
    if not argv:
        return argv
    if not shutil.which("systemd-run"):
        return argv
    if use_user is None:
        use_user = os.geteuid() != 0 and Path("/run/systemd/system").exists()
    base = ["systemd-run", "--user", "--scope", "--slice=gaming.slice"] if use_user else ["systemd-run", "--scope", "--slice=gaming.slice"]
    return base + ["--"] + argv


def is_gaming_slice_available() -> bool:
    return bool(shutil.which("systemd-run") and Path("/usr/lib/systemd/system/gaming.slice").exists())
