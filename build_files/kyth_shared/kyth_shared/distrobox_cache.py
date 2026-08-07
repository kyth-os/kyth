"""Distrobox cache — distrobox-cache.toml, tmpfs 4G + ccache + cargo."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_DISTROBOX_CACHE_PATH = Path("/etc/kyth/distrobox-cache.toml")
DEFAULT_TMPFILES = Path("/etc/tmpfiles.d/99-kyth-distrobox.conf")
DEFAULT_SERVICE = Path("/etc/systemd/system/kyth-distrobox-cache.service")


def distrobox_cache_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "distrobox-cache.toml"
    return DEFAULT_DISTROBOX_CACHE_PATH


def load_distrobox_cache(path: Path | None = None) -> dict[str, Any]:
    p = distrobox_cache_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"enabled": False, "size": "4G", "ccache_size": "10G"}
    en = bool(data.get("enabled", False))
    size = str(data.get("size", "4G"))
    if size not in ("2G", "4G", "8G"):
        size = "4G"
    csz = str(data.get("ccache_size", "10G"))
    if csz not in ("5G", "10G", "20G"):
        csz = "10G"
    return {"enabled": en, "size": size, "ccache_size": csz}


def save_distrobox_cache(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = distrobox_cache_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    en = bool(cfg.get("enabled", False))
    size = str(cfg.get("size", "4G"))
    csz = str(cfg.get("ccache_size", "10G"))
    p.write_text(f"# Kyth distrobox cache — offline\nenabled = {str(en).lower()}\nsize = \"{size}\"\nccache_size = \"{csz}\"\n", encoding="utf-8")
    return p


def generate_distrobox_cache(cfg: dict[str, Any] | None = None, tmpfiles: Path | None = None, service: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_distrobox_cache()
    tmpfiles = tmpfiles or DEFAULT_TMPFILES
    service = service or DEFAULT_SERVICE
    if not cfg.get("enabled"):
        for d in (tmpfiles, service):
            try:
                if d.exists():
                    d.unlink()
            except OSError:
                pass
        return None
    size = str(cfg.get("size", "4G"))
    csz = str(cfg.get("ccache_size", "10G"))
    try:
        tmpfiles.parent.mkdir(parents=True, exist_ok=True)
        tmpfiles.write_text(f"# Kyth distrobox cache — generated\nd /run/kyth-distrobox-cache 0755 1000 1000 -\n", encoding="utf-8")
    except OSError:
        pass
    content = f"""[Unit]
Description=Kyth distrobox cache — tmpfs for ccache/cargo
After=local-fs.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'mkdir -p /run/kyth-distrobox-cache && mount -t tmpfs -o size={size},mode=0755 tmpfs /run/kyth-distrobox-cache && mkdir -p /run/kyth-distrobox-cache/ccache /run/kyth-distrobox-cache/cargo && ccache --max-size={csz} 2>/dev/null || true'
ExecStop=/bin/sh -c 'umount /run/kyth-distrobox-cache 2>/dev/null || true'
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
    return service


def distrobox_cache_status(service: Path = DEFAULT_SERVICE) -> str:
    return "enabled" if service.exists() else "off"
