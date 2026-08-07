"""RGB preset — rgb.toml openrgb/liquidctl, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_RGB_PATH = Path.home() / ".config" / "kyth" / "rgb.toml"

def rgb_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"rgb.toml"
    return DEFAULT_RGB_PATH

def load_rgb(path: Path | None = None) -> dict[str, dict[str, Any]]:
    p=rgb_config_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out={}
    for dev, e in data.get("devices", {}).items() if isinstance(data.get("devices"), dict) else []:
        if not isinstance(e, dict):
            continue
        out[str(dev)]={"effect": str(e.get("effect","rainbow")), "brightness": max(0, min(100, int(e.get("brightness",80)))), "color": str(e.get("color","#ffffff"))}
    return out

def save_rgb(devices: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    p=rgb_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth RGB per-device, offline\n"]
    for dev in sorted(devices):
        e=devices[dev]
        lines.append(f'[devices."{dev}"]')
        lines.append(f'effect = "{e.get("effect","rainbow")}"')
        lines.append(f'brightness = {int(e.get("brightness",80))}')
        lines.append(f'color = "{e.get("color","#ffffff")}"')
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p
