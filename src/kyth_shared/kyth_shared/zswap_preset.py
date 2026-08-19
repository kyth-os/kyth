"""Zswap — zswap.toml declarative, offline.

Complements zram on <16GB rigs. kyth enables zswap zstd, balanced removes.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_ZSWAP_PATH = Path("/etc/kyth/zswap.toml")
DEFAULT_CONF = Path("/etc/sysctl.d/99-kyth-zswap.conf")
DEFAULT_MOD = Path("/etc/modprobe.d/99-kyth-zswap.conf")


def zswap_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "zswap.toml"
    return DEFAULT_ZSWAP_PATH


def load_zswap(path: Path | None = None) -> dict[str, Any]:
    p = zswap_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced", "compressor": "zstd", "zpool": "zsmalloc"}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in ("balanced", "kyth"):
        prof = "balanced"
    comp = str(data.get("compressor", "zstd"))
    if comp not in ("zstd", "lz4", "lzo"):
        comp = "zstd"
    zpool = str(data.get("zpool", "zsmalloc"))
    if zpool not in ("zsmalloc", "zbud", "z3fold"):
        zpool = "zsmalloc"
    return {"profile": prof, "compressor": comp, "zpool": zpool}


def save_zswap(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = zswap_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "kyth"):
        prof = "balanced"
    comp = str(cfg.get("compressor", "zstd"))
    zpool = str(cfg.get("zpool", "zsmalloc"))
    lines = ["# Kyth zswap — offline\n", f'profile = "{prof}"\n', f'compressor = "{comp}"\n', f'zpool = "{zpool}"\n']
    p.write_text("".join(lines), encoding="utf-8")
    return p


def generate_zswap(cfg: dict[str, Any] | None = None, conf: Path | None = None, mod: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_zswap()
    conf = conf or DEFAULT_CONF
    mod = mod or DEFAULT_MOD
    if str(cfg.get("profile", "balanced")) != "kyth":
        for d in (conf, mod):
            try:
                if d.exists():
                    d.unlink()
            except OSError:
                pass
        return None
    comp = str(cfg.get("compressor", "zstd"))
    zpool = str(cfg.get("zpool", "zsmalloc"))
    conf.parent.mkdir(parents=True, exist_ok=True)
    mod.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text(f"# Kyth zswap — generated\nvm.zswap_enabled = 1\nvm.zswap_compressor = {comp}\nvm.zswap_zpool = {zpool}\n", encoding="utf-8")
    tmp = mod.with_suffix(".tmp")
    tmp.write_text(f"# Kyth zswap — generated\noptions zswap enabled=1 compressor={comp} zpool={zpool}\n", encoding="utf-8")
    tmp.replace(mod)
    return conf


def zswap_status(conf: Path = DEFAULT_CONF) -> str:
    return "kyth" if conf.exists() else "balanced"
