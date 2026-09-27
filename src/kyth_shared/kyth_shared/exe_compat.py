"""EXE compat checker — compat.json offline Wine/Bottles/Proton per exe sha256."""
from __future__ import annotations

import hashlib, json, shutil
from pathlib import Path
from typing import Any

from kyth_shared.commands import run as run_command

DEFAULT_COMPAT_PATH = Path("/usr/share/kyth/compat.json")

def compat_path(path: Path | None = None) -> Path:
    return Path(path) if path else DEFAULT_COMPAT_PATH

def load_compat(path: Path | None = None) -> dict[str, Any]:
    p=compat_path(path)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        return {"entries": {}}

def bottles_available() -> bool:
    """True when a Bottles runner is actually installed (native or Flatpak)."""
    if shutil.which("bottles-cli") or shutil.which("bottles"):
        return True
    flatpak = shutil.which("flatpak")
    if flatpak:
        try:
            res = run_command(
                [flatpak, "info", "com.usebottles.bottles"],
                capture_output=True, timeout=10, check=False,
            )
            if res.returncode == 0:
                return True
        except (OSError, ValueError, RuntimeError):
            pass
    return False

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
    if bottles_available():
        return {"status": "Works", "runner": "Bottles", "reason": "Offline DB: best-effort Wine"}
    return {
        "status": "Unknown",
        "runner": "Wine (unverified)",
        "reason": "Bottles is not installed, so this could not be verified — try Bottles, Lutris, or plain Wine",
    }
