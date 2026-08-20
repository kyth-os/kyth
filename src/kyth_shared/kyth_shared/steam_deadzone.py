"""Steam deadzone calibrate — 5% gaming vs balanced, per-controller."""
from __future__ import annotations
import logging

import os, tomllib
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_STEAM_DEADZONE_PATH = Path("/etc/kyth/steam-deadzone.toml")


def steam_deadzone_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "steam-deadzone.toml"
    return DEFAULT_STEAM_DEADZONE_PATH


def load_steam_deadzone(path: Path | None = None) -> dict[str, Any]:
    p = steam_deadzone_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced", "deadzone": 0.15}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    try:
        dz = float(data.get("deadzone", 0.05 if prof == "gaming" else 0.15))
    except (TypeError, ValueError):
        dz = 0.05 if prof == "gaming" else 0.15
    dz = max(0.0, min(0.3, dz))
    return {"profile": prof, "deadzone": dz}


def save_steam_deadzone(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = steam_deadzone_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    dz = float(cfg.get("deadzone", 0.05 if prof == "gaming" else 0.15))
    p.write_text(f"# Kyth steam deadzone — offline\nprofile = \"{prof}\"\ndeadzone = {dz}\n", encoding="utf-8")
    return p


def apply_steam_deadzone(cfg: dict[str, Any] | None = None) -> bool:
    if cfg is None:
        cfg = load_steam_deadzone()
    dz = float(cfg.get("deadzone", 0.15))
    # also update steam-input per-game deadzones
    try:
        from .steam_input import load_steam_input, save_steam_input

        games = load_steam_input()
        if not games:
            return True
        for app in games:
            games[app]["deadzone"] = dz
        save_steam_input(games)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass
    return True
