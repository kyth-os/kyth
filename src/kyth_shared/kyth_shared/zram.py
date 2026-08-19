"""Zram swap tiering — zram.toml, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_ZRAM_PATH = Path("/etc/kyth/zram.toml")

def zram_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1":
        return Path(xdg)/"kyth"/"zram.toml"
    return DEFAULT_ZRAM_PATH

def load_zram(path: Path | None = None) -> dict[str, Any]:
    p=zram_config_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"zram_percent": 50, "swappiness": 180, "algorithm": "zstd"}
    return {"zram_percent": max(10, min(100, int(data.get("zram_percent",50)))), "swappiness": max(0, min(200, int(data.get("swappiness",180)))), "algorithm": str(data.get("algorithm","zstd"))}

def save_zram(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=zram_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth zram — offline\n"]
    lines.append(f'zram_percent = {int(cfg.get("zram_percent",50))}')
    lines.append(f'swappiness = {int(cfg.get("swappiness",180))}')
    lines.append(f'algorithm = "{cfg.get("algorithm","zstd")}"')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p

def generate_zram_conf(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path:
    if cfg is None:
        cfg=load_zram()
    dest=dest or Path("/etc/systemd/zram-generator.conf")
    dest.parent.mkdir(parents=True, exist_ok=True)
    content=f"[zram0]\nzram-size = ram / {int(100/cfg['zram_percent'])}\ncompression-algorithm = {cfg['algorithm']}\nswap-priority = 100\n"
    tmp=dest.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    return dest
