"""Input preset — input.toml per-device libinput, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_INPUT_PATH = Path.home() / ".config" / "kyth" / "input.toml"

def input_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"input.toml"
    return DEFAULT_INPUT_PATH

def load_input(path: Path | None = None) -> dict[str, dict[str, Any]]:
    p=input_config_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out={}
    for dev, e in data.get("devices", {}).items() if isinstance(data.get("devices"), dict) else []:
        if not isinstance(e, dict):
            continue
        out[str(dev)]={"accel_profile": str(e.get("accel_profile","adaptive")) if str(e.get("accel_profile","adaptive")) in ("adaptive","flat") else "adaptive",
                       "accel_speed": max(-1.0, min(1.0, float(e.get("accel_speed",0)))), "tap_to_click": bool(e.get("tap_to_click", False)),
                       "scroll_method": str(e.get("scroll_method","twofinger"))}
    return out

def save_input(devices: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    p=input_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth input per-device libinput\n"]
    for dev in sorted(devices):
        e=devices[dev]
        lines.append(f'[devices."{dev}"]')
        lines.append(f'accel_profile = "{e.get("accel_profile","adaptive")}"')
        lines.append(f'accel_speed = {float(e.get("accel_speed",0))}')
        lines.append(f'tap_to_click = {str(bool(e.get("tap_to_click",False))).lower()}')
        lines.append(f'scroll_method = "{e.get("scroll_method","twofinger")}"')
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p
