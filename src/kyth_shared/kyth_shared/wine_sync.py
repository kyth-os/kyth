"""Wine sync — wine-sync.toml, probes ntsync/futex2, writes env."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_text

DEFAULT_WINE_SYNC_PATH = Path("/etc/kyth/wine-sync.toml")
DEFAULT_ENV = Path("/etc/environment.d/99-kyth-wine-sync.conf")


def wine_sync_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "wine-sync.toml"
    return DEFAULT_WINE_SYNC_PATH


def probe_wine_sync() -> dict[str, bool]:
    ntsync = Path("/dev/ntsync").exists() or Path("/sys/module/ntsync").exists()
    # futex2 landed in 5.16. Do not treat a "6." substring in /proc/version
    # as proof — that string shows up in lots of banners and would enable
    # WINEFSYNC on kernels that don't have it.
    futex2 = False
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8").strip()
        version = release.split("-", 1)[0]
        parts = [int(p) for p in version.split(".")[:2]]
        futex2 = tuple(parts) >= (5, 16)
    except (OSError, ValueError):
        pass
    return {"ntsync": ntsync, "futex2": futex2, "esync": True, "fsync": True}


def load_wine_sync(path: Path | None = None) -> dict[str, Any]:
    p = wine_sync_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"mode": "auto"}
    mode = str(data.get("mode", "auto")).lower()
    if mode not in ("auto", "ntsync", "fsync", "esync", "off"):
        mode = "auto"
    return {"mode": mode}


def save_wine_sync(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = wine_sync_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = str(cfg.get("mode", "auto")).lower()
    if mode not in ("auto", "ntsync", "fsync", "esync", "off"):
        mode = "auto"
    atomic_write_text(p, f"# Kyth wine sync — offline\nmode = \"{mode}\"\n", mode=0o600)
    return p


def generate_wine_env(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_wine_sync()
    dest = dest or DEFAULT_ENV
    mode = str(cfg.get("mode", "auto")).lower()
    if mode == "off":
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None
    if mode == "auto":
        probe = probe_wine_sync()
        if probe["ntsync"]:
            mode = "ntsync"
        elif probe["futex2"]:
            mode = "fsync"
        else:
            mode = "esync"
    env = {
        "ntsync": "WINEFSYNC=1\nNTSYNC=1\n",
        "fsync": "WINEFSYNC=1\n",
        "esync": "WINEESYNC=1\n",
    }.get(mode, "WINEFSYNC=1\n")
    content = f"# Kyth wine sync — generated {mode}\n{env}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    return dest


def wine_sync_status(env: Path = DEFAULT_ENV) -> str:
    if not env.exists():
        return "off"
    try:
        t = env.read_text(encoding="utf-8")
        if "NTSYNC" in t:
            return "ntsync"
        if "WINEFSYNC" in t:
            return "fsync"
        if "WINEESYNC" in t:
            return "esync"
    except OSError:
        pass
    return "unknown"
