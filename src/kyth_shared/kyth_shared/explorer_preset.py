"""Explorer parity — explorer.toml Dolphin double-click + preview + drives."""
from __future__ import annotations
import logging

import os
import tomllib
from pathlib import Path
from typing import Any
from kyth_shared.commands import run

from .atomic_io import atomic_write_text as _atomic_write_text

logger = logging.getLogger(__name__)

DEFAULT_EXPLORER_PATH = Path.home() / ".config" / "kyth" / "explorer.toml"

def explorer_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"explorer.toml"
    return DEFAULT_EXPLORER_PATH

def load_explorer(path: Path | None = None) -> dict[str, Any]:
    p=explorer_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return {"click": "double", "preview": True, "drives_on_desktop": True}
    click=str(data.get("click","double")) if str(data.get("click","double")) in ("single","double") else "double"
    return {"click": click, "preview": bool(data.get("preview", True)), "preview_pane": bool(data.get("preview_pane", True)), "drives_on_desktop": bool(data.get("drives_on_desktop", True))}

def save_explorer(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=explorer_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth Explorer parity — Windows double-click + preview + drives\n"]
    lines.append(f'click = "{cfg.get("click","double")}"')
    lines.append(f'preview = {str(bool(cfg.get("preview",True))).lower()}')
    lines.append(f'preview_pane = {str(bool(cfg.get("preview_pane",True))).lower()}')
    lines.append(f'drives_on_desktop = {str(bool(cfg.get("drives_on_desktop",True))).lower()}')
    _atomic_write_text(p, "\n".join(lines)+"\n", encoding="utf-8")
    return p

def apply_explorer(cfg: dict[str, Any] | None = None) -> list[str]:
    if cfg is None:
        cfg=load_explorer()
    applied=[]
    single = "true" if cfg["click"]=="single" else "false"
    try:
        run(["kwriteconfig5","--file","kdeglobals","--group","KDE","--key","SingleClick", single], capture_output=True, timeout=5)
        applied.append(f"SingleClick={single}")
    except (OSError, ValueError) as exc:
        logger.debug("apply_explorer SingleClick failed: %s", exc, exc_info=True)
        pass
    try:
        run(["kwriteconfig5","--file","dolphinrc","--group","General","--key","ShowPreview", str(cfg["preview"]).lower()], capture_output=True, timeout=5)
    except (OSError, ValueError) as exc:
        logger.debug("apply_explorer ShowPreview failed: %s", exc, exc_info=True)
        pass
    # Drives on desktop via Desktop .desktop already via NTFS D: — no extra
    try:
        import time; _atomic_write_text(Path("/run/kyth-explorer-ttl"), str(int(time.time())+30), encoding="utf-8")
    except (OSError, ValueError) as exc:
        logger.debug("apply_explorer ttl write failed: %s", exc, exc_info=True)
        pass
    return applied
