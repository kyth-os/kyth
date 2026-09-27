"""Steam deadzone calibrate — 5% gaming vs balanced, per-controller."""
from __future__ import annotations
import logging

import os, tomllib
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_text

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
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    try:
        dz = float(cfg.get("deadzone", 0.05 if prof == "gaming" else 0.15))
    except (TypeError, ValueError):
        dz = 0.05 if prof == "gaming" else 0.15
    dz = max(0.0, min(0.3, dz))
    lines = [
        "# Kyth steam deadzone — offline",
        f'profile = "{prof}"',
        f"deadzone = {dz}",
        "",
    ]
    atomic_write_text(p, "\n".join(lines), mode=0o600)
    return p


def apply_steam_deadzone(cfg: dict[str, Any] | None = None) -> bool:
    if cfg is None:
        cfg = load_steam_deadzone()
    dz = float(cfg.get("deadzone", 0.15))
    # Seed-only: fill in games that have no deadzone yet. Per-game values the
    # user (or Steam) already set are never overwritten — the old blanket loop
    # reset every custom deadzone on each apply.
    try:
        from .steam_input import load_steam_input, save_steam_input

        games = load_steam_input()
        if not games:
            return True
        changed = False
        for app in games:
            if games[app].get("deadzone") is None:
                games[app]["deadzone"] = dz
                changed = True
        if changed:
            save_steam_input(games)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass
    return True
