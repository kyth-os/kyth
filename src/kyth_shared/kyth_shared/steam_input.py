"""Steam Input preset — steam-input.toml per-game, offline.

A per-game ``deadzone`` is explicit only when present in the file; games
without one inherit the global steam-deadzone profile at read time via
:func:`effective_deadzone` and are never overwritten by it.
"""
from __future__ import annotations

import json
import os, tomllib
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_text

DEFAULT_STEAM_INPUT_PATH = Path.home() / ".config" / "kyth" / "steam-input.toml"

#: Fallback when neither a per-game value nor a global profile provides one.
DEFAULT_DEADZONE = 0.2

def steam_input_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"steam-input.toml"
    return DEFAULT_STEAM_INPUT_PATH

def _clamp_deadzone(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return None

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
        out[str(app)]={"layout": str(e.get("layout","gamepad")), "gyro": bool(e.get("gyro", False)), "deadzone": _clamp_deadzone(e.get("deadzone"))}
    return out

def save_steam_input(games: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    p=steam_input_path(path)
    lines=["# Kyth Steam Input per-game"]
    for app in sorted(games):
        app_id = str(app)
        if not app_id or any(c in app_id for c in "\n\r"):
            continue
        lines.append(f"[games.{json.dumps(app_id, ensure_ascii=False)}]")
        layout = str(games[app].get("layout","gamepad"))
        lines.append(f"layout = {json.dumps(layout, ensure_ascii=False)}")
        lines.append(f'gyro = {str(bool(games[app].get("gyro",False))).lower()}')
        dz = _clamp_deadzone(games[app].get("deadzone"))
        if dz is not None:
            lines.append(f'deadzone = {dz}')
        lines.append("")
    atomic_write_text(p, "\n".join(lines)+"\n", mode=0o600)
    return p

def effective_deadzone(app: str, games: dict[str, dict[str, Any]] | None = None, global_deadzone: float = DEFAULT_DEADZONE) -> float:
    """Per-game deadzone when explicit, else the global profile default."""
    if games is None:
        games = load_steam_input()
    entry = games.get(app, {})
    dz = _clamp_deadzone(entry.get("deadzone"))
    if dz is not None:
        return dz
    try:
        return max(0.0, min(1.0, float(global_deadzone)))
    except (TypeError, ValueError):
        return DEFAULT_DEADZONE
