"""Window snap parity — window-snap.toml Win+Arrow, offline."""
from __future__ import annotations
import logging

import os, tomllib
from pathlib import Path
from typing import Any
from kyth_shared.commands import run

logger = logging.getLogger(__name__)

DEFAULT_SNAP_PATH = Path.home() / ".config" / "kyth" / "window-snap.toml"

def snap_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"window-snap.toml"
    return DEFAULT_SNAP_PATH

def load_snap(path: Path | None = None) -> dict[str, Any]:
    p=snap_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"layout": "2x2", "win_z": True, "electric": True}
    layout=str(data.get("layout","2x2")) if str(data.get("layout","2x2")) in ("2x2","3col","off") else "2x2"
    return {"layout": layout, "win_z": bool(data.get("win_z", True)), "electric": bool(data.get("electric", True))}

def save_snap(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=snap_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth window snap — Win+Arrow, offline\n"]
    lines.append(f'layout = "{cfg.get("layout","2x2")}"')
    lines.append(f'win_z = {str(bool(cfg.get("win_z",True))).lower()}')
    lines.append(f'electric = {str(bool(cfg.get("electric",True))).lower()}')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p

def apply_snap(cfg: dict[str, Any] | None = None) -> list[str]:
    if cfg is None:
        cfg=load_snap()
    applied=[]
    try:
        run(["kwriteconfig5","--file","kwinrc","--group","Windows","--key","ElectricBorder","--type","bool", str(cfg["electric"]).lower()], capture_output=True, timeout=5)
        applied.append("kwinrc ElectricBorder")
    except Exception:
        logger.debug("handled expected exception", exc_info=True)
        pass
    # Win+Arrow shortcuts: quick tile left/right via kglobalshortcutsrc (best-effort)
    for act, key in [("Window Quick Tile Left","Meta+Left"),("Window Quick Tile Right","Meta+Right"),("Window Maximize","Meta+Up")]:
        try:
            run(["kwriteconfig5","--file","kglobalshortcutsrc","--group","kwin","--key", act, f"{key},none,{act}"], capture_output=True, timeout=5)
        except Exception:
            logger.debug("handled expected exception", exc_info=True)
            pass
    try:
        import time; Path("/run/kyth-snap-ttl").write_text(str(int(time.time())+30), encoding="utf-8")
    except Exception:
        logger.debug("handled expected exception", exc_info=True)
        pass
    return applied
