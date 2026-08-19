"""Gaming snapshot — pre-master btrfs snapshot helper, offline."""
from __future__ import annotations
import logging

from typing import Any

from .commands import run

logger = logging.getLogger(__name__)


def create_pre_gaming_snapshot(description: str = "pre-gaming-master") -> dict[str, Any]:
    """Create snapshot via snapper or btrfs; returns result dict."""
    # try snapper
    try:
        r = run(["snapper", "create", "--description", description, "--print-number"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return {"ok": True, "id": r.stdout.strip(), "tool": "snapper"}
    except Exception:
        logger.debug("handled expected exception", exc_info=True)
        pass
    try:
        r = run(["btrfs", "subvolume", "snapshot", "-r", "/", f"/.snapshots/pre-gaming-{description}"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return {"ok": True, "id": description, "tool": "btrfs"}
    except Exception:
        logger.debug("handled expected exception", exc_info=True)
        pass
    return {"ok": False, "error": "no snapper/btrfs available — snapshot skipped (safe to proceed)"}


def ensure_snapshot_before_master() -> dict[str, Any]:
    return create_pre_gaming_snapshot("pre-gaming-master")
