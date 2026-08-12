"""Shader pipeline cache — fossilize content-hashed preheat.

Offline, no cloud. Hashes glsl/spirv + driver version, stores under /var/cache/kyth/shaders/<appid>/<hash>/ (fossilize replay + DXVK_STATE_CACHE + RADV). Mirrors gaming_per_game preset style, hash-gated.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

DEFAULT_CACHE_ROOT = Path("/var/cache/kyth/shaders")


def cache_root(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    return DEFAULT_CACHE_ROOT


def content_hash_for_appid(appid: str, driver_version: str, glsl_text: str = "") -> str:
    h = hashlib.sha256()
    h.update(appid.encode())
    h.update(b"\0")
    h.update(driver_version.encode())
    h.update(b"\0")
    h.update(glsl_text.encode())
    return h.hexdigest()[:12]


def cache_dir_for_appid(appid: str, driver_version: str, glsl_text: str = "", root: Path | None = None) -> Path:
    root = cache_root(root)
    ch = content_hash_for_appid(appid, driver_version, glsl_text)
    return root / str(appid) / ch


def preheat_status(appid: str, driver_version: str, root: Path | None = None) -> dict[str, object]:
    d = cache_dir_for_appid(appid, driver_version, root=root)
    exists = d.exists()
    files = list(d.glob("*")) if exists else []
    return {"cached": exists, "files": len(files), "path": str(d), "hash": d.name}


def ensure_cache_dir(appid: str, driver_version: str, glsl_text: str = "", root: Path | None = None) -> Path:
    d = cache_dir_for_appid(appid, driver_version, glsl_text, root=root)
    d.mkdir(parents=True, exist_ok=True)
    return d
