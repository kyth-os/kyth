"""Save cloud — restic local repo + rclone optional, per-game saves offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_SAVE_CLOUD_PATH = Path.home() / ".config" / "kyth" / "save-cloud.toml"

def save_cloud_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"save-cloud.toml"
    return DEFAULT_SAVE_CLOUD_PATH

def load_save_cloud(path: Path | None = None) -> dict[str, Any]:
    p=save_cloud_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"repo": "/var/cache/kyth/saves", "remote": "", "on_battery": False}
    return {"repo": str(data.get("repo","/var/cache/kyth/saves")), "remote": str(data.get("remote","")), "on_battery": bool(data.get("on_battery", False))}

def save_save_cloud(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=save_cloud_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth save cloud — restic local + rclone remote, offline\n"]
    lines.append(f'repo = "{cfg.get("repo","/var/cache/kyth/saves")}"')
    lines.append(f'remote = "{cfg.get("remote","")}"')
    lines.append(f'on_battery = {str(bool(cfg.get("on_battery", False))).lower()}')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p
