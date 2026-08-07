"""Work cache — work-cache.toml, tmpfs for Code/cargo."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_WORK_CACHE_PATH = Path("/etc/kyth/work-cache.toml")
DEFAULT_TMPFILES = Path("/etc/tmpfiles.d/99-kyth-work-cache.conf")
DEFAULT_SERVICE = Path("/etc/systemd/system/kyth-work-cache.service")


def work_cache_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "work-cache.toml"
    return DEFAULT_WORK_CACHE_PATH


def load_work_cache(path: Path | None = None) -> dict[str, Any]:
    p = work_cache_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"enabled": False, "size": "1G"}
    en = bool(data.get("enabled", False))
    size = str(data.get("size", "1G"))
    if size not in ("1G", "2G", "4G"):
        size = "1G"
    return {"enabled": en, "size": size}


def save_work_cache(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = work_cache_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    en = bool(cfg.get("enabled", False))
    size = str(cfg.get("size", "1G"))
    p.write_text(f"# Kyth work cache — offline\nenabled = {str(en).lower()}\nsize = \"{size}\"\n", encoding="utf-8")
    return p


def generate_work_cache(cfg: dict[str, Any] | None = None, tmpfiles: Path | None = None, service: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_work_cache()
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
    size = str(cfg.get("size", "1G"))
    try:
        tmpfiles.parent.mkdir(parents=True, exist_ok=True)
        tmpfiles.write_text(f"# Kyth work cache — generated\nd /run/kyth-work-cache 0755 1000 1000 -\n", encoding="utf-8")
    except OSError:
        pass
    content = f"""[Unit]
Description=Kyth work cache — Code/cargo tmpfs
After=local-fs.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'mkdir -p /run/kyth-work-cache && mount -t tmpfs -o size={size},mode=0755 tmpfs /run/kyth-work-cache && mkdir -p /run/kyth-work-cache/vscode /run/kyth-work-cache/cargo && mount --bind /run/kyth-work-cache/vscode ~/.vscode-server 2>/dev/null || true; mount --bind /run/kyth-work-cache/cargo ~/.cargo/registry 2>/dev/null || true'
ExecStop=/bin/sh -c 'umount ~/.vscode-server 2>/dev/null || true; umount ~/.cargo/registry 2>/dev/null || true; umount /run/kyth-work-cache 2>/dev/null || true'
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


def work_cache_status(service: Path = DEFAULT_SERVICE) -> str:
    return "enabled" if service.exists() else "off"
