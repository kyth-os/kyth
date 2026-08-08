"""Snapshot autoclean — qgroup quota + snapper TTL, offline."""
from __future__ import annotations

from pathlib import Path
from kyth_shared.commands import run

def autoclean(home: Path = Path("/home"), limit_percent: int = 20) -> dict[str, str]:
    # Check btrfs
    try:
        r=run(["btrfs","filesystem","show", str(home)], capture_output=True, timeout=5)
        if r.returncode!=0:
            return {"status":"not-btrfs"}
    except Exception:
        return {"status":"no-btrfs"}
    # Set qgroup limit if snapper present
    try:
        # enable quota if not
        run(["btrfs","quota","enable", str(home)], capture_output=True, timeout=5)
        # limit via qgroup (best-effort)
        run(["btrfs","qgroup","limit", f"{limit_percent}%", str(home)], capture_output=True, timeout=5)
    except Exception:
        pass
    # Snapper cleanup
    try:
        run(["snapper","-c","root","set-config","TIMELINE_LIMIT_HOURLY=5","TIMELINE_LIMIT_DAILY=7","TIMELINE_LIMIT_MONTHLY=2"], capture_output=True, timeout=5)
        run(["snapper","cleanup","timeline"], capture_output=True, timeout=10)
    except Exception:
        pass
    return {"status":"ok", "limit": f"{limit_percent}%"}
