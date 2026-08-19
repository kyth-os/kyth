"""Overlay per-game MangoHud+vkBasalt — overlay.toml, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

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
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth per-game overlay MangoHud+vkBasalt\n"]
    for app in sorted(games):
        lines.append(f'[games."{app}"]')
        lines.append(f'mangohud_layout = "{games[app].get("mangohud_layout","fps+frametime")}"')
        lines.append(f'vkbasalt = "{games[app].get("vkbasalt","off")}"')
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p

def env_for_app(app: str, path: Path | None = None) -> dict[str,str]:
    cfg=load_overlay(path).get(str(app),{})
    env={}
    if cfg.get("mangohud_layout") and cfg["mangohud_layout"]!="off":
        env["MANGOHUD_CONFIG"] = cfg["mangohud_layout"]
    if cfg.get("vkbasalt")=="cas":
        env["ENABLE_VKBASALT"]="1"
    return env
