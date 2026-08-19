"""Fcitx5 latency — 10ms gaming vs 50ms balanced."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_text as _atomic_write_text

DEFAULT_FCITX_LATENCY_PATH = Path("/etc/kyth/fcitx-latency.toml")


def fcitx_latency_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "fcitx-latency.toml"
    return DEFAULT_FCITX_LATENCY_PATH


def load_fcitx_latency(path: Path | None = None) -> dict[str, Any]:
    p = fcitx_latency_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced", "latency_ms": 50}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    try:
        lat = int(data.get("latency_ms", 10 if prof == "gaming" else 50))
    except (TypeError, ValueError):
        lat = 10 if prof == "gaming" else 50
    lat = max(5, min(100, lat))
    return {"profile": prof, "latency_ms": lat}


def save_fcitx_latency(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = fcitx_latency_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    lat = int(cfg.get("latency_ms", 10 if prof == "gaming" else 50))
    _atomic_write_text(p, f"# Kyth fcitx5 latency — offline\nprofile = \"{prof}\"\nlatency_ms = {lat}\n", encoding="utf-8")
    return p


def apply_fcitx_latency(cfg: dict[str, Any] | None = None) -> bool:
    if cfg is None:
        cfg = load_fcitx_latency()
    lat = int(cfg.get("latency_ms", 50))
    conf = Path.home() / ".config/fcitx5/config"
    if not conf.exists():
        return False
    try:
        t = conf.read_text(encoding="utf-8")
        if "Latency" in t:
            import re

            t = re.sub(r"Latency=\\d+", f"Latency={lat}", t)
            _atomic_write_text(conf, t, encoding="utf-8")
            return True
    except OSError:
        pass
    return False
