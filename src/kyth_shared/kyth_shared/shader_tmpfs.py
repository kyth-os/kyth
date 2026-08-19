"""Shader tmpfs — shader-tmpfs.toml, mesa cache on tmpfs + persist."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_SHADER_TMPFS_PATH = Path("/etc/kyth/shader-tmpfs.toml")
DEFAULT_FSTAB_DROPIN = Path("/etc/systemd/system/home.mount.d/99-kyth-shader.conf")  # placeholder, actual fstab handled via helper
DEFAULT_TMPFS = Path("/etc/tmpfiles.d/99-kyth-shader.conf")
DEFAULT_MOUNT_UNIT = Path("/etc/systemd/system/kyth-shader-tmpfs.service")


def shader_tmpfs_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "shader-tmpfs.toml"
    return DEFAULT_SHADER_TMPFS_PATH


def load_shader_tmpfs(path: Path | None = None) -> dict[str, Any]:
    p = shader_tmpfs_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"enabled": False, "size": "2G"}
    en = bool(data.get("enabled", False))
    size = str(data.get("size", "2G"))
    if size not in ("1G", "2G", "4G"):
        size = "2G"
    return {"enabled": en, "size": size}


def save_shader_tmpfs(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = shader_tmpfs_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    en = bool(cfg.get("enabled", False))
    size = str(cfg.get("size", "2G"))
    p.write_text(f"# Kyth shader tmpfs — offline\nenabled = {str(en).lower()}\nsize = \"{size}\"\n", encoding="utf-8")
    return p


def generate_shader_tmpfs(cfg: dict[str, Any] | None = None, tmpfiles: Path | None = None, service: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_shader_tmpfs()
    tmpfiles = tmpfiles or DEFAULT_TMPFS
    service = service or DEFAULT_MOUNT_UNIT
    if not cfg.get("enabled"):
        for d in (tmpfiles, service):
            try:
                if d.exists():
                    d.unlink()
            except OSError:
                pass
        return None
    size = str(cfg.get("size", "2G"))
    try:
        tmpfiles.parent.mkdir(parents=True, exist_ok=True)
        tmpfiles.write_text(f"# Kyth shader tmpfs — generated\nd /run/kyth-shader 0755 {os.getuid() if hasattr(os, 'getuid') else 1000} {os.getgid() if hasattr(os, 'getgid') else 1000} -\n", encoding="utf-8")
    except OSError:
        pass
    content = f"""[Unit]
Description=Kyth shader tmpfs — mesa cache on tmpfs
After=local-fs.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'mkdir -p /run/kyth-shader && mount -t tmpfs -o size={size},mode=0755 tmpfs /run/kyth-shader && mkdir -p ~/.cache/mesa_shader_cache && mount --bind /run/kyth-shader ~/.cache/mesa_shader_cache 2>/dev/null || true'
ExecStop=/bin/sh -c 'rsync -a /run/kyth-shader/ ~/.cache/mesa_shader_cache.persist/ 2>/dev/null || true; umount ~/.cache/mesa_shader_cache 2>/dev/null || true; umount /run/kyth-shader 2>/dev/null || true'
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


def shader_tmpfs_status(service: Path = DEFAULT_MOUNT_UNIT) -> str:
    return "enabled" if service.exists() else "off"
