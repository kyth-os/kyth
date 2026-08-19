"""Backup Full — backup.toml restic+btrfs send for /home, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_BACKUP_PATH = Path("/etc/kyth/backup.toml")

def backup_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1":
        return Path(xdg)/"kyth"/"backup.toml"
    return DEFAULT_BACKUP_PATH

def load_backup(path: Path | None = None) -> dict[str, Any]:
    p=backup_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"repo": "/var/cache/kyth/backup", "btrfs_send": False, "on_battery": False, "remote": ""}
    return {"repo": str(data.get("repo","/var/cache/kyth/backup")), "btrfs_send": bool(data.get("btrfs_send", False)), "on_battery": bool(data.get("on_battery", False)), "remote": str(data.get("remote",""))}

def save_backup(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=backup_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth backup full /home\n"]
    lines.append(f'repo = "{cfg.get("repo","/var/cache/kyth/backup")}"')
    lines.append(f'btrfs_send = {str(bool(cfg.get("btrfs_send", False))).lower()}')
    lines.append(f'on_battery = {str(bool(cfg.get("on_battery", False))).lower()}')
    lines.append(f'remote = "{cfg.get("remote","")}"')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p
