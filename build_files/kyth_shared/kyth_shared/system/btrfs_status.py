"""btrfs status helper — surface maint.jsonl + scrub status (N16).

Mint Timeshift parity: readable btrfs health without new daemon.
Uses existing kyth-btrfs-maint maint.jsonl 1M rotation.
"""
from __future__ import annotations

import json
from pathlib import Path

_MAINT = Path("/var/log/kyth/maint.jsonl")


def btrfs_health_summary() -> tuple[str, str]:
    """Return (status, detail) for Health dashboard. Never raises."""
    try:
        from kyth_shared.commands import run as _run

        r = _run(["btrfs", "scrub", "status", "/"], capture_output=True, text=True, timeout=5, check=False)
        if r.returncode == 0 and "running" in getattr(r, "stdout", "").lower():
            return "warn", "btrfs scrub running"
    except Exception:
        pass
    try:
        if _MAINT.exists():
            # last line is most recent maint
            line = _MAINT.read_text(errors="ignore").strip().splitlines()[-1]
            data = json.loads(line)
            return str(data.get("status", "ok")), str(data.get("msg", "btrfs maint idle"))
    except Exception:
        pass
    return "ok", "btrfs maint idle (PSI/AC gated)"
