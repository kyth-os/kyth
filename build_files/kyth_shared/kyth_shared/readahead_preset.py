"""Readahead — readahead.toml declarative, offline.

Ephemeral WILLNEED on game dirs, no daemon. gaming wrapper calls helper.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_READAHEAD_PATH = Path("/etc/kyth/readahead.toml")


def readahead_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "readahead.toml"
    return DEFAULT_READAHEAD_PATH


def load_readahead(path: Path | None = None) -> dict[str, Any]:
    p = readahead_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"enabled": True, "size_mb": 512}
    return {"enabled": bool(data.get("enabled", True)), "size_mb": max(64, min(4096, int(data.get("size_mb", 512))))}


def save_readahead(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = readahead_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    en = bool(cfg.get("enabled", True))
    sz = max(64, min(4096, int(cfg.get("size_mb", 512))))
    p.write_text(f"# Kyth readahead — offline\nchecked = {str(en).lower()}\nenabled = {str(en).lower()}\nsize_mb = {sz}\n", encoding="utf-8")
    return p


def readahead_for_path(target: Path, size_mb: int = 512) -> int:
    """Fadvise WILLNEED up to size_mb files under target. Returns files touched."""
    if not target.exists():
        return 0
    import os

    count = 0
    limit = size_mb * 1024 * 1024
    seen = 0
    for f in target.rglob("*"):
        if seen >= limit:
            break
        if not f.is_file():
            continue
        try:
            fd = os.open(str(f), os.O_RDONLY)
            try:
                os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_WILLNEED)
            finally:
                os.close(fd)
            count += 1
            seen += f.stat().st_size
        except OSError:
            pass
    return count
