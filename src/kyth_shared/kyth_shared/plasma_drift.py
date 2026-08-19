"""Plasma drift reconciler — plasma.toml declarative, offline."""
from __future__ import annotations
import logging

import os
import tomllib
from pathlib import Path
from typing import Any
from kyth_shared.commands import run

from .atomic_io import atomic_write_text as _atomic_write_text

logger = logging.getLogger(__name__)

DEFAULT_PLASMA_PATH = Path.home() / ".config" / "kyth" / "plasma.toml"

def plasma_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"plasma.toml"
    return DEFAULT_PLASMA_PATH

def load_plasma(path: Path | None = None) -> dict[str, dict[str, Any]]:
    p=plasma_config_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return {}
    out={}
    for sec, kv in data.items():
        if not isinstance(kv, dict):
            continue
        out[str(sec)]={str(k): str(v) for k,v in kv.items()}
    return out

def save_plasma(sections: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    p=plasma_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth Plasma drift — declarative, offline\n"]
    for sec in sorted(sections):
        lines.append(f"[{sec}]")
        for k,v in sorted(sections[sec].items()):
            lines.append(f'{k} = "{v}"')
        lines.append("")
    _atomic_write_text(p, "\n".join(lines), encoding="utf-8")
    return p

def apply_plasma(sections: dict[str, dict[str, Any]] | None = None) -> list[str]:
    if sections is None:
        sections=load_plasma()
    applied=[]
    for sec, kv in sections.items():
        for k,v in kv.items():
            # kwriteconfig5/6 best-effort
            for bin_name in ("kwriteconfig6","kwriteconfig5","kwriteconfig"):
                try:
                    r=run([bin_name,"--file", sec, "--group", "General","--key", k, str(v)], capture_output=True, timeout=5)
                    if r.returncode==0:
                        applied.append(f"{sec}:{k}={v}")
                        break
                except (OSError, ValueError):
                    continue
    # reconfigure KWin best-effort
    try:
        run(["qdbus","org.kde.KWin","/KWin","reconfigure"], capture_output=True, timeout=5)
    except (OSError, ValueError) as exc:
        logger.debug("plasma reconfigure failed: %s", exc, exc_info=True)
        pass
    try:
        import time; _atomic_write_text(Path("/run/kyth-plasma-ttl"), str(int(time.time())+30), encoding="utf-8")
    except (OSError, ValueError) as exc:
        logger.debug("plasma ttl write failed: %s", exc, exc_info=True)
        pass
    return applied
