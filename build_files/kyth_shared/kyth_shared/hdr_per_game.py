"""HDR per-game — hdr-per-game.toml, peak per steam-appid."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_HDR_PER_GAME_PATH = Path.home() / ".config/kyth/hdr-per-game.toml"


def hdr_per_game_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"hdr-per-game.toml"
    return DEFAULT_HDR_PER_GAME_PATH


def load_hdr_per_game(path: Path | None = None) -> dict[str,Any]:
    p=hdr_per_game_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out={}
    for app, e in data.get("games",{}).items() if isinstance(data.get("games"), dict) else []:
        if not isinstance(e, dict):
            continue
        try:
            peak=int(e.get("peak_nits",400))
        except Exception:
            peak=400
        peak=max(100, min(4000, peak))
        out[str(app)]={"peak_nits":peak,"itm": bool(e.get("itm", False))}
    return out


def save_hdr_per_game(games: dict[str,Any], path: Path | None = None) -> Path:
    p=hdr_per_game_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth HDR per-game — offline\n"]
    for app in sorted(games):
        lines.append(f'[games."{app}"]')
        lines.append(f'peak_nits = {games[app].get("peak_nits",400)}')
        lines.append(f'itm = {str(bool(games[app].get("itm", False))).lower()}')
        lines.append("")
    p.write_text("\n".join(lines),encoding="utf-8")
    return p


def hdr_for_app(app: str, path: Path | None = None) -> dict[str,Any]|None:
    return load_hdr_per_game(path).get(str(app))
