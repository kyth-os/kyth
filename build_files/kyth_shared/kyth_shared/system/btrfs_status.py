"""btrfs status helper — surface maint.jsonl + scrub status (N16).

Mint Timeshift parity: readable btrfs health without new daemon.
Uses existing kyth-btrfs-maint maint.jsonl 1M rotation.
"""
from __future__ import annotations
import logging

import json
from pathlib import Path

logger = logging.getLogger(__name__)

_MAINT = Path("/var/log/kyth/maint.jsonl")


def btrfs_health_summary() -> tuple[str, str]:
    """Return (status, detail) for Health dashboard. Never raises."""
    try:
        from kyth_shared.commands import run as _run

        r = _run(["btrfs", "scrub", "status", "/"], capture_output=True, text=True, timeout=5, check=False)
        if r.returncode == 0 and "running" in getattr(r, "stdout", "").lower():
            return "warn", "btrfs scrub running"
    except Exception:
        logger.debug("handled expected exception", exc_info=True)
        pass
    try:
        if _MAINT.exists():
            # last line is most recent maint
            line = _MAINT.read_text(errors="ignore").strip().splitlines()[-1]
            data = json.loads(line)
            return str(data.get("status", "ok")), str(data.get("msg", "btrfs maint idle"))
    except Exception:
        logger.debug("handled expected exception", exc_info=True)
        pass
    return "ok", "btrfs maint idle (PSI/AC gated)"
