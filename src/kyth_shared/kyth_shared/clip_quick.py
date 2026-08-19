"""Clip + Quick Settings — quick.toml klipper + quicksettings, offline."""
from __future__ import annotations
import logging

import os, tomllib
from pathlib import Path
from typing import Any
from kyth_shared.commands import run

logger = logging.getLogger(__name__)

DEFAULT_QUICK_PATH = Path.home() / ".config" / "kyth" / "quick.toml"

def quick_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"quick.toml"
    return DEFAULT_QUICK_PATH

def load_quick(path: Path | None = None) -> dict[str, Any]:
    p=quick_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return {"clip_history": 20, "tiles": ["wifi","bt","night"]}
    return {"clip_history": max(5, min(100, int(data.get("clip_history",20)))), "tiles": [str(x) for x in data.get("tiles", ["wifi","bt","night"]) if str(x) in ("wifi","bt","night","plane")] or ["wifi","bt","night"]}

def save_quick(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=quick_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth quick settings + clip\n"]
    lines.append(f'clip_history = {int(cfg.get("clip_history",20))}')
    tiles=cfg.get("tiles",["wifi","bt","night"])
    lines.append(f'tiles = {tiles}')
    import tempfile

    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=f".{p.name}.")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
            f.flush()
            os.fsync(f.fileno())
        Path(tmp).replace(p)
        try:
            dfd = os.open(str(p.parent), os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except (OSError, ValueError):
            pass
    except BaseException:
        try:
            Path(tmp).unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
        raise
    return p

def apply_quick(cfg: dict[str, Any] | None = None) -> list[str]:
    if cfg is None:
        cfg=load_quick()
    applied=[]
    try:
        run(["kwriteconfig5","--file","klipperrc","--group","General","--key","KeepClipboardContents", str(cfg["clip_history"]>0).lower()], capture_output=True, timeout=5)
        run(["kwriteconfig5","--file","klipperrc","--group","General","--key","MaxClipItems", str(cfg["clip_history"])], capture_output=True, timeout=5)
        applied.append("klipperrc")
    except (OSError, ValueError) as exc:
        logger.debug("apply_quick klipperrc failed: %s", exc, exc_info=True)
        pass
    return applied
