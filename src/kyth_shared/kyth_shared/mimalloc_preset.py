"""Mimalloc gaming — mimalloc.toml declarative, offline.

Per-game LD_PRELOAD wrapper, no global preload. Off by default.
On writes 99-kyth-mimalloc.conf environment.d for opt-in + provides
mimalloc-run helper.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_MIMALLOC_PATH = Path("/etc/kyth/mimalloc.toml")
DEFAULT_ENV = Path("/etc/environment.d/99-kyth-mimalloc.conf")


def mimalloc_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "mimalloc.toml"
    return DEFAULT_MIMALLOC_PATH


def load_mimalloc(path: Path | None = None) -> dict[str, Any]:
    p = mimalloc_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"enabled": False, "global": False, "per_game": True}
    return {
        "enabled": bool(data.get("enabled", False)),
        "global": bool(data.get("global", False)),
        "per_game": bool(data.get("per_game", True)),
    }


def save_mimalloc(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = mimalloc_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    en = bool(cfg.get("enabled", False))
    gl = bool(cfg.get("global", False))
    pg = bool(cfg.get("per_game", True))
    lines = [
        "# Kyth mimalloc — offline, per-game wrapper\n",
        f"enabled = {str(en).lower()}\n",
        f"global = {str(gl).lower()}\n",
        f"per_game = {str(pg).lower()}\n",
    ]
    p.write_text("".join(lines), encoding="utf-8")
    return p


def _find_lib() -> str:
    for cand in ("/usr/lib64/libmimalloc.so.2", "/usr/lib64/libmimalloc.so", "/usr/lib/libmimalloc.so"):
        if Path(cand).exists():
            return cand
    return "/usr/lib64/libmimalloc.so.2"


def generate_mimalloc_env(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_mimalloc()
    dest = dest or DEFAULT_ENV
    if not cfg.get("enabled") or not cfg.get("global"):
        try:
            if dest.exists() and "Kyth" in dest.read_text(encoding="utf-8"):
                dest.unlink()
        except OSError:
            pass
        return None
    lib = _find_lib()
    content = f"# Kyth mimalloc — generated, global preload (opt-in)\nLD_PRELOAD={lib}\nMIMALLOC_LARGE_OS_PAGES=1\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    return dest


def mimalloc_status(env: Path = DEFAULT_ENV) -> str:
    if env.exists():
        return "global"
    cfg = load_mimalloc()
    if cfg.get("enabled"):
        return "per-game"
    return "off"
