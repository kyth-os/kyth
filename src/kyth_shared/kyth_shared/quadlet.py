"""Quadlet gaming services — quadlet.toml declarative podman."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_QUADLET_PATH = Path.home() / ".config" / "kyth" / "quadlet.toml"

def quadlet_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"quadlet.toml"
    return DEFAULT_QUADLET_PATH

def load_quadlet(path: Path | None = None) -> dict[str, dict[str, Any]]:
    p=quadlet_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out={}
    for name, e in data.get("services", {}).items() if isinstance(data.get("services"), dict) else []:
        if not isinstance(e, dict):
            continue
        out[str(name)]={"image": str(e.get("image","")), "auto": bool(e.get("auto", False))}
    return out

def save_quadlet(services: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    p=quadlet_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth quadlet gaming services\n"]
    for name in sorted(services):
        lines.append(f'[services."{name}"]')
        lines.append(f'image = "{services[name].get("image","")}"')
        lines.append(f'auto = {str(bool(services[name].get("auto",False))).lower()}')
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p
