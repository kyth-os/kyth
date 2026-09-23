"""Distrobox cache — distrobox-cache.toml, tmpfs 4G + ccache + cargo."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_text

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
        with p.open("rb") as _f:
            data = tomllib.load(_f)
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


_DISTROBOX_SIZES = ("2G", "4G", "8G")
_DISTROBOX_CCACHE_SIZES = ("5G", "10G", "20G")


def _norm_distrobox_size(value: Any, default: str = "4G") -> str:
    size = str(value or default)
    return size if size in _DISTROBOX_SIZES else default


def _norm_ccache_size(value: Any, default: str = "10G") -> str:
    size = str(value or default)
    return size if size in _DISTROBOX_CCACHE_SIZES else default


def save_distrobox_cache(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = distrobox_cache_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    en = bool(cfg.get("enabled", False))
    # Normalize against the allowlist even on save: the TOML is re-read by
    # load_*, but save_ also round-trips through callers that may feed the
    # dict straight into generate_ — never persist a hostile string.
    size = _norm_distrobox_size(cfg.get("size"))
    csz = _norm_ccache_size(cfg.get("ccache_size"))
    atomic_write_text(
        p,
        f"# Kyth distrobox cache — offline\nenabled = {str(en).lower()}\nsize = \"{size}\"\nccache_size = \"{csz}\"\n",
        mode=0o600,
    )
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
    # Normalize inside generate_ too: callers may pass a dict that never
    # went through load_ (e.g. the generic generate_tunable path), and the
    # sizes land inside a root /bin/sh -c line.
    size = _norm_distrobox_size(cfg.get("size"))
    csz = _norm_ccache_size(cfg.get("ccache_size"))
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
