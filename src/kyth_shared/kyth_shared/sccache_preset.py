"""Sccache — sccache.toml, 10G cache for Rust/C."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_SCCACHE_PATH = Path("/etc/kyth/sccache.toml")
DEFAULT_ENV = Path("/etc/environment.d/99-kyth-sccache.conf")
DEFAULT_SERVICE = Path("/etc/systemd/system/sccache.service")


def sccache_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "sccache.toml"
    return DEFAULT_SCCACHE_PATH


def load_sccache(path: Path | None = None) -> dict[str, Any]:
    p = sccache_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"enabled": False, "size": "10G"}
    en = bool(data.get("enabled", False))
    size = str(data.get("size", "10G"))
    if size not in ("5G", "10G", "20G", "50G"):
        size = "10G"
    return {"enabled": en, "size": size}


def save_sccache(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = sccache_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    en = bool(cfg.get("enabled", False))
    size = str(cfg.get("size", "10G"))
    p.write_text(f"# Kyth sccache — offline\nenabled = {str(en).lower()}\nsize = \"{size}\"\n", encoding="utf-8")
    return p


def generate_sccache(cfg: dict[str, Any] | None = None, env: Path | None = None, service: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_sccache()
    env = env or DEFAULT_ENV
    service = service or DEFAULT_SERVICE
    if not cfg.get("enabled"):
        for d in (env, service):
            try:
                if d.exists():
                    d.unlink()
            except OSError:
                pass
        return None
    size = str(cfg.get("size", "10G"))
    try:
        env.parent.mkdir(parents=True, exist_ok=True)
        env.write_text(f"# Kyth sccache — generated\nSCCACHE_DIR=/var/cache/sccache\nSCCACHE_CACHE_SIZE={size}\n", encoding="utf-8")
    except OSError:
        pass
    content = f"""[Unit]
Description=Kyth sccache server — Rust/C cache
After=network.target
[Service]
Type=simple
Environment=SCCACHE_DIR=/var/cache/sccache
Environment=SCCACHE_CACHE_SIZE={size}
ExecStart=/usr/bin/sccache --start-server
ExecStop=/usr/bin/sccache --stop-server
Restart=on-failure
[Install]
WantedBy=multi-user.target
"""
    try:
        service.parent.mkdir(parents=True, exist_ok=True)
        tmp = service.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(service)
    except OSError:
        return None
    return env


def sccache_status(env: Path = DEFAULT_ENV) -> str:
    return "enabled" if env.exists() else "off"
