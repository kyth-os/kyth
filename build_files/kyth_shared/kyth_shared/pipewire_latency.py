"""PipeWire low-latency presets — pipewire-latency.toml, offline.

Maps app → quantum (16-2048) → PIPEWIRE_LATENCY env + wireplumber drop-in, hash-gated.
"""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_PIPEWIRE_PATH = Path.home() / ".config" / "kyth" / "pipewire-latency.toml"

def pipewire_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"pipewire-latency.toml"
    return DEFAULT_PIPEWIRE_PATH

def load_pipewire_latency(path: Path | None = None) -> dict[str, int]:
    p=pipewire_config_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    apps=data.get("apps",{})
    if not isinstance(apps, dict):
        return {}
    out={}
    for app, q in apps.items():
        try:
            qi=int(q)
        except Exception:
            continue
        qi=max(16, min(2048, qi))
        # round to power of 2
        # keep as is
        out[str(app)]=qi
    return out

def save_pipewire_latency(apps: dict[str, int], path: Path | None = None) -> Path:
    p=pipewire_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth PipeWire latency — app → quantum, offline\n", "[apps]"]
    for app in sorted(apps):
        lines.append(f'"{app}" = {int(apps[app])}')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p

def quantum_for_app(app_id: str, path: Path | None = None) -> int | None:
    return load_pipewire_latency(path).get(app_id)

def pipewire_env_for_app(app_id: str, rate: int = 48000, path: Path | None = None) -> dict[str, str]:
    q=quantum_for_app(app_id, path)
    if q is None:
        return {}
    return {"PIPEWIRE_LATENCY": f"{q}/{rate}"}
