"""Print/Scan autopilot — print.toml ipp-usb + sane-airscan, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_PRINT_PATH = Path("/etc/kyth/print.toml")

def print_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1":
        return Path(xdg)/"kyth"/"print.toml"
    return DEFAULT_PRINT_PATH

def load_print(path: Path | None = None) -> dict[str, Any]:
    p=print_config_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"auto_add": True, "airscan": True}
    return {"auto_add": bool(data.get("auto_add", True)), "airscan": bool(data.get("airscan", True))}

def save_print(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=print_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth Print/Scan autopilot\n"]
    lines.append(f'auto_add = {str(bool(cfg.get("auto_add",True))).lower()}')
    lines.append(f'airscan = {str(bool(cfg.get("airscan",True))).lower()}')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p
