"""Boot loader fast-path — loader.toml, greenboot-aware timeout 0 vs 2s."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_LOADER_PATH = Path("/etc/kyth/loader.toml")
DEFAULT_LOADER_CONF = Path("/boot/loader/loader.conf")


def loader_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "loader.toml"
    return DEFAULT_LOADER_PATH


def load_loader(path: Path | None = None) -> dict[str, Any]:
    p = loader_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"fast": False, "timeout": 2}
    fast = bool(data.get("fast", False))
    try:
        to = int(data.get("timeout", 0 if fast else 2))
    except (TypeError, ValueError):
        to = 0 if fast else 2
    to = max(0, min(10, to))
    return {"fast": fast, "timeout": to}


def save_loader(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = loader_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fast = bool(cfg.get("fast", False))
    try:
        to = int(cfg.get("timeout", 0 if fast else 2))
    except (TypeError, ValueError):
        to = 0 if fast else 2
    to = max(0, min(10, to))
    p.write_text(f"# Kyth loader — offline\nfast = {str(fast).lower()}\ntimeout = {to}\n", encoding="utf-8")
    return p


def generate_loader_conf(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_loader()
    dest = dest or DEFAULT_LOADER_CONF
    if not cfg.get("fast"):
        # restore default 2s by removing override if we created it
        try:
            if dest.exists() and "Kyth" in dest.read_text(encoding="utf-8"):
                # set to 2s instead of unlink to keep file
                dest.write_text("timeout 2\n", encoding="utf-8")
        except OSError:
            pass
        return None
    to = int(cfg.get("timeout", 0))
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = f"# Kyth loader fast-path — generated, greenboot-aware\ntimeout {to}\n"
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    return dest


def loader_status(conf: Path = DEFAULT_LOADER_CONF) -> str:
    if not conf.exists():
        return "balanced"
    try:
        t = conf.read_text(encoding="utf-8")
        if "timeout 0" in t:
            return "fast"
        if "Kyth" in t:
            return "fast"
    except OSError:
        pass
    return "balanced"
