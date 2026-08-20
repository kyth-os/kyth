"""EXE compat checker — compat.json offline Wine/Bottles/Proton per exe sha256."""
from __future__ import annotations

import hashlib, json
from pathlib import Path
from typing import Any

DEFAULT_COMPAT_PATH = Path("/usr/share/kyth/compat.json")

def compat_path(path: Path | None = None) -> Path:
    return Path(path) if path else DEFAULT_COMPAT_PATH

def load_compat(path: Path | None = None) -> dict[str, Any]:
    p=compat_path(path)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        return {"entries": {}}

def check_exe(exe_path: Path | str, compat: dict[str, Any] | None = None) -> dict[str, str]:
    if compat is None:
        compat=load_compat()
    p=Path(exe_path)
    try:
        h=hashlib.sha256(p.read_bytes()[:1<<20]).hexdigest()[:12] if p.exists() else "unknown"
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        h="unknown"
    entries=compat.get("entries", {}) if isinstance(compat, dict) else {}
    # lookup by hash or by name
    key = h if h in entries else p.name.lower() if p.name.lower() in entries else None
    if key and key in entries:
        e=entries[key]
        return {"status": str(e.get("status","Works")), "runner": str(e.get("runner","Wine")), "reason": str(e.get("reason",""))}
    # heuristic: anti-cheat names
    name=p.name.lower()
    for bad in ("easyanticheat","eac","vgc","battleye"):
        if bad in name:
            return {"status": "Blocked", "runner": "Anti-cheat", "reason": f"Contains {bad} — blocked"}
    return {"status": "Works", "runner": "Bottles", "reason": "Offline DB: best-effort Wine"}
