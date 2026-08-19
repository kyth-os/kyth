"""VRR + Night color scheduler — vrr.toml per-output, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_VRR_PATH = Path.home() / ".config" / "kyth" / "vrr.toml"

def vrr_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"vrr.toml"
    return DEFAULT_VRR_PATH

def load_vrr(path: Path | None = None) -> dict[str, Any]:
    p=vrr_config_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"outputs": {}, "night": {"enabled": False, "temperature": 4500}}
    outs={}
    for conn, e in data.get("outputs", {}).items() if isinstance(data.get("outputs"), dict) else []:
        if not isinstance(e, dict):
            continue
        vrr=str(e.get("vrr","adaptive"))
        if vrr not in ("adaptive","always","never"):
            vrr="adaptive"
        outs[str(conn)]={"vrr": vrr}
    night=data.get("night",{})
    if not isinstance(night, dict):
        night={}
    enabled=bool(night.get("enabled", False))
    try:
        temp=int(night.get("temperature", 4500))
    except Exception:
        temp=4500
    temp=max(2000, min(6500, temp))
    return {"outputs": outs, "night": {"enabled": enabled, "temperature": temp}}

def save_vrr(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=vrr_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth VRR + night color, offline\n"]
    for conn in sorted(cfg.get("outputs", {})):
        lines.append(f'[outputs."{conn}"]')
        lines.append(f'vrr = "{cfg["outputs"][conn].get("vrr","adaptive")}"')
        lines.append("")
    lines.append("[night]")
    lines.append(f'enabled = {str(bool(cfg["night"].get("enabled", False))).lower()}')
    lines.append(f'temperature = {int(cfg["night"].get("temperature",4500))}')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p
