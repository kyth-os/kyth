"""Snapshot timeline — btrfs + bootc image list, offline.

Parses `snapper list --json` / `btrfs subvolume list` + `bootc status --json` into timeline rows for Hub.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kyth_shared.commands import run


@dataclass(frozen=True, slots=True)
class SnapshotRow:
    id: str
    timestamp: str
    type: str  # snapshot | deployment | rollback
    description: str
    healthy: bool | None = None


def _snapper_rows() -> list[SnapshotRow]:
    try:
        r = run(["snapper", "list", "--json"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout:
            data = json.loads(r.stdout)
            rows = []
            for s in data.get("snapshots", []) if isinstance(data, dict) else []:
                rows.append(SnapshotRow(id=str(s.get("number", "")), timestamp=str(s.get("date", "")), type="snapshot", description=str(s.get("description", ""))))
            return rows
    except Exception:
        pass
    # btrfs fallback
    try:
        r = run(["btrfs", "subvolume", "list", "/"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            rows = []
            for line in r.stdout.splitlines()[:20]:
                rows.append(SnapshotRow(id=line.split()[1] if len(line.split())>1 else "", timestamp="", type="snapshot", description=line[:80]))
            return rows
    except Exception:
        pass
    return []


def _bootc_rows() -> list[SnapshotRow]:
    try:
        r = run(["bootc", "status", "--json"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout:
            data = json.loads(r.stdout)
            rows = []
            for k in ("booted", "rollback", "staged"):
                img = data.get("status", {}).get(k, {}) if isinstance(data, dict) else {}
                if not img:
                    continue
                digest = img.get("imageDigest", img.get("image", {}).get("imageDigest", "")) if isinstance(img, dict) else ""
                rows.append(SnapshotRow(id=digest[:12] if digest else k, timestamp="", type="deployment" if k=="booted" else "rollback", description=f"{k}: {digest[:40]}"))
            return rows
    except Exception:
        pass
    return []


def snapshot_timeline(limit: int = 20) -> list[SnapshotRow]:
    rows = _snapper_rows() + _bootc_rows()
    # de-duplicate, keep order
    seen = set()
    out = []
    for r in rows:
        key = (r.id, r.type)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
        if len(out) >= limit:
            break
    return out


def snapshot_timeline_json(limit: int = 20) -> str:
    return json.dumps([r.__dict__ for r in snapshot_timeline(limit)], indent=2)
