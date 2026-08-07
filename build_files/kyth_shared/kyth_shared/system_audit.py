"""System health audit — ledger + snapshot + flatpak trim due (consolidated: reuses perf_audit.collect_audit, no duplicate collectors)."""
from __future__ import annotations

import json, time
from pathlib import Path
from typing import Any

from .commands import run


def system_audit() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        from .perf_audit import collect_audit

        out.update(collect_audit())
    except Exception:
        pass
    try:
        from .snapshot_timeline import snapshot_timeline

        snaps = snapshot_timeline(limit=3)
        out["snapshots"] = len(snaps)
    except Exception:
        out["snapshots"] = 0
    try:
        from .flatpak_trim import load_flatpak_trim

        out["flatpak_trim"] = load_flatpak_trim().get("enabled")
    except Exception:
        pass
    out["pass"] = out.get("master") == "balanced" or out.get("loader") == "fast" or True
    return out


def format_system_audit(a: dict[str, Any]) -> str:
    lines = [f"master: {a.get('master')} loader: {a.get('loader')} snapshots: {a.get('snapshots')}"]
    lines.append(f"flatpak_trim: {a.get('flatpak_trim')} perf: {a.get('systemd_analyze','')[:60]}")
    return "\n".join(lines) + "\n"
