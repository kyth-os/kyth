"""PipeWire gaming — pipewire-gaming.toml, wireplumber drop-in only in gaming.

Quantum 128/48000 for low latency, otherwise 1024/48000 studio.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_PIPEWIRE_GAMING_PATH = Path("/etc/kyth/pipewire-gaming.toml")
DEFAULT_CONF = Path("/etc/wireplumber/main.lua.d/99-kyth-gaming.lua")


def pipewire_gaming_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "pipewire-gaming.toml"
    return DEFAULT_PIPEWIRE_GAMING_PATH


def load_pipewire_gaming(path: Path | None = None) -> dict[str, Any]:
    p = pipewire_gaming_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced", "quantum": 128}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    try:
        q = int(data.get("quantum", 128))
    except (TypeError, ValueError):
        q = 128
    q = max(32, min(2048, q))
    return {"profile": prof, "quantum": q}


def save_pipewire_gaming(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = pipewire_gaming_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    q = int(cfg.get("quantum", 128))
    p.write_text(f"# Kyth PipeWire gaming — offline\nprofile = \"{prof}\"\nquantum = {q}\n", encoding="utf-8")
    return p


def generate_pipewire_gaming(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_pipewire_gaming()
    dest = dest or DEFAULT_CONF
    if str(cfg.get("profile", "balanced")) != "gaming":
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None
    q = int(cfg.get("quantum", 128))
    content = (
        "-- Kyth PipeWire gaming — generated\n"
        'table.insert(alsa_monitor.rules, {\n'
        '  matches = {{{ "node.name", "matches", "alsa_output.*" }}},\n'
        '  apply_properties = {\n'
        f'    ["api.alsa.period-size"] = {q},\n'
        f'    ["api.alsa.headroom"] = {q},\n'
        '  },\n'
        '})\n'
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    return dest


def pipewire_gaming_status(conf: Path = DEFAULT_CONF) -> str:
    return "gaming" if conf.exists() else "balanced"
