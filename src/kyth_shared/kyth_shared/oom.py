"""Systemd-OOMD tuned — oom.toml per-cgroup, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_OOM_PATH = Path("/etc/kyth/oom.toml")

def oom_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1":
        return Path(xdg)/"kyth"/"oom.toml"
    return DEFAULT_OOM_PATH

def load_oom(path: Path | None = None) -> dict[str, Any]:
    p=oom_config_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"default_mem_pressure_limit": "50%", "gaming_preference": "avoid"}
    return {"default_mem_pressure_limit": str(data.get("default_mem_pressure_limit","50%")), "gaming_preference": str(data.get("gaming_preference","avoid"))}

def save_oom(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=oom_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth OOMD tuned\n"]
    lines.append(f'default_mem_pressure_limit = "{cfg.get("default_mem_pressure_limit","50%")}"')
    lines.append(f'gaming_preference = "{cfg.get("gaming_preference","avoid")}"')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p
