"""SCX per-game preset — scx.toml explicit, offline.

Complements ai_perf TTL (explicit wins). Maps app → scx.
"""
from __future__ import annotations

import os, tomllib
from pathlib import Path

DEFAULT_SCX_PRESET_PATH = Path.home() / ".config" / "kyth" / "scx.toml"

def scx_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"scx.toml"
    return DEFAULT_SCX_PRESET_PATH

def load_scx_preset(path: Path | None = None) -> dict[str, str]:
    p=scx_config_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out={}
    for app, v in data.get("games", {}).items() if isinstance(data.get("games"), dict) else []:
        scx=str(v.get("scx","")) if isinstance(v, dict) else str(v)
        if scx in ("scx_rusty","scx_bpfland","scx_lavd","none"):
            out[str(app)]=scx
    return out

def save_scx_preset(games: dict[str, str], path: Path | None = None) -> Path:
    p=scx_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth SCX per-game, explicit wins over TTL\n"]
    for app in sorted(games):
        lines.append(f'[games."{app}"]')
        lines.append(f'scx = "{games[app]}"')
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p

def scx_for_app(app: str, path: Path | None = None) -> str | None:
    return load_scx_preset(path).get(str(app))
