"""Overlay per-game MangoHud+vkBasalt — overlay.toml, offline."""
from __future__ import annotations

import json
import os, tomllib
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_text

DEFAULT_OVERLAY_PATH = Path.home() / ".config" / "kyth" / "overlay.toml"

def overlay_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"overlay.toml"
    return DEFAULT_OVERLAY_PATH

def load_overlay(path: Path | None = None) -> dict[str, dict[str, Any]]:
    p=overlay_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out={}
    for app, e in data.get("games", {}).items() if isinstance(data.get("games"), dict) else []:
        if not isinstance(e, dict):
            continue
        out[str(app)]={"mangohud_layout": str(e.get("mangohud_layout","fps+frametime")), "vkbasalt": str(e.get("vkbasalt","off")) if str(e.get("vkbasalt","off")) in ("cas","off","sharp") else "off"}
    return out

def save_overlay(games: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    p=overlay_path(path)
    lines=["# Kyth per-game overlay MangoHud+vkBasalt\n"]
    for app in sorted(games):
        app_id = str(app)
        if not app_id or any(c in app_id for c in "\n\r"):
            continue
        layout = str(games[app].get("mangohud_layout","fps+frametime"))
        vk = str(games[app].get("vkbasalt","off"))
        if vk not in ("cas","off","sharp"):
            vk = "off"
        lines.append(f"[games.{json.dumps(app_id, ensure_ascii=False)}]")
        lines.append(f"mangohud_layout = {json.dumps(layout, ensure_ascii=False)}")
        lines.append(f"vkbasalt = {json.dumps(vk)}")
        lines.append("")
    atomic_write_text(p, "\n".join(lines), mode=0o600)
    return p

def env_for_app(app: str, path: Path | None = None) -> dict[str,str]:
    cfg=load_overlay(path).get(str(app),{})
    env={}
    if cfg.get("mangohud_layout") and cfg["mangohud_layout"]!="off":
        env["MANGOHUD_CONFIG"] = cfg["mangohud_layout"]
    if cfg.get("vkbasalt")=="cas":
        env["ENABLE_VKBASALT"]="1"
    return env
