"""Podman btrfs — podman-btrfs.toml, driver btrfs when on btrfs."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_PODMAN_BTRFS_PATH = Path("/etc/kyth/podman-btrfs.toml")
DEFAULT_CONF = Path("/etc/containers/storage.conf.d/99-kyth-btrfs.conf")


def podman_btrfs_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "podman-btrfs.toml"
    return DEFAULT_PODMAN_BTRFS_PATH


def load_podman_btrfs(path: Path | None = None) -> dict[str, Any]:
    p = podman_btrfs_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"mode": "auto"}
    mode = str(data.get("mode", "auto")).lower()
    if mode not in ("auto", "btrfs", "overlay", "off"):
        mode = "auto"
    return {"mode": mode}


def save_podman_btrfs(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = podman_btrfs_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = str(cfg.get("mode", "auto")).lower()
    if mode not in ("auto", "btrfs", "overlay", "off"):
        mode = "auto"
    p.write_text(f"# Kyth podman btrfs — offline\nmode = \"{mode}\"\n", encoding="utf-8")
    return p


def _on_btrfs() -> bool:
    try:

        from .commands import run as _run

        r = _run(["findmnt", "-no", "FSTYPE", "-T", "/var"], capture_output=True, text=True, timeout=5)
        return bool(r and "btrfs" in r.stdout)
    except Exception:
        pass
    try:
        return "btrfs" in Path("/proc/mounts").read_text(encoding="utf-8")
    except OSError:
        return False


def generate_podman_btrfs(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_podman_btrfs()
    dest = dest or DEFAULT_CONF
    mode = str(cfg.get("mode", "auto"))
    if mode == "off":
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None
    if mode == "auto":
        mode = "btrfs" if _on_btrfs() else "overlay"
    if mode not in ("btrfs", "overlay"):
        mode = "overlay"
    # overlay is default, no drop-in needed
    if mode == "overlay":
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None
    content = '# Kyth podman btrfs — generated\n[storage]\ndriver = "btrfs"\n'
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    return dest


def podman_btrfs_status(conf: Path = DEFAULT_CONF) -> str:
    if conf.exists():
        try:
            return "btrfs" if "btrfs" in conf.read_text(encoding="utf-8") else "overlay"
        except OSError:
            return "unknown"
    return "overlay" if not _on_btrfs() else "overlay (auto)"
