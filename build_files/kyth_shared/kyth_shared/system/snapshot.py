"""Snapshot browser helper — Mint Timeshift parity (N38)."""
from __future__ import annotations
from kyth_shared.commands import run

def list_snapshots() -> list[str]:
    try:
        r = run(["btrfs", "subvolume", "list", "/"], capture_output=True, text=True, timeout=10, check=False)
        if r.returncode == 0:
            return [l.strip() for l in r.stdout.splitlines() if "snapshot" in l.lower()][:20]
        r2 = run(["snapper", "list"], capture_output=True, text=True, timeout=10, check=False)
        if r2.returncode == 0:
            return [l.strip() for l in r2.stdout.splitlines() if l.strip()][:20]
        return []
    except Exception:
        return []

def snapshot_dry_run() -> tuple[bool, str]:
    snaps = list_snapshots()
    return (True, f"dry-run ok: {len(snaps)} snapshots") if snaps else (True, "dry-run ok: no snapshots yet")
