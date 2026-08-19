"""Steam Input preset — steam-input.toml per-game, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_STEAM_INPUT_PATH = Path.home() / ".config" / "kyth" / "steam-input.toml"

def steam_input_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"steam-input.toml"
    return DEFAULT_STEAM_INPUT_PATH

def load_steam_input(path: Path | None = None) -> dict[str, dict[str, Any]]:
    p=steam_input_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out={}
    for app, e in data.get("games", {}).items() if isinstance(data.get("games"), dict) else []:
        if not isinstance(e, dict):
            continue
        out[str(app)]={"layout": str(e.get("layout","gamepad")), "gyro": bool(e.get("gyro", False)), "deadzone": max(0.0, min(1.0, float(e.get("deadzone", 0.2))))}
    return out

def save_steam_input(games: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    p=steam_input_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth Steam Input per-game\n"]
    for app in sorted(games):
        lines.append(f'[games."{app}"]')
        lines.append(f'layout = "{games[app].get("layout","gamepad")}"')
        lines.append(f'gyro = {str(bool(games[app].get("gyro",False))).lower()}')
        lines.append(f'deadzone = {float(games[app].get("deadzone",0.2))}')
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p
