"""Bluetooth LE Audio preset — bluetooth.toml per-device, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_BT_PATH = Path.home() / ".config" / "kyth" / "bluetooth.toml"

def bt_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"bluetooth.toml"
    return DEFAULT_BT_PATH

def load_bt(path: Path | None = None) -> dict[str, dict[str, Any]]:
    p=bt_config_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out={}
    for addr, e in data.get("devices", {}).items() if isinstance(data.get("devices"), dict) else []:
        if not isinstance(e, dict):
            continue
        out[str(addr)]={"codec": str(e.get("codec","LC3")), "latency": str(e.get("latency","low"))}
    return out

def save_bt(devices: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    p=bt_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth Bluetooth LE Audio per-device\n"]
    for addr in sorted(devices):
        lines.append(f'[devices."{addr}"]')
        lines.append(f'codec = "{devices[addr].get("codec","LC3")}"')
        lines.append(f'latency = "{devices[addr].get("latency","low")}"')
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p
