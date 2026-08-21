"""Window snap parity — window-snap.toml Win+Arrow via kwriteconfig6."""
from __future__ import annotations

import logging
import os
import shutil
import tomllib
from pathlib import Path
from typing import Any

from kyth_shared.commands import run

from .atomic_io import atomic_write_text as _atomic_write_text

logger = logging.getLogger(__name__)

DEFAULT_SNAP_PATH = Path.home() / ".config" / "kyth" / "window-snap.toml"


def snap_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "kyth" / "window-snap.toml"
    return DEFAULT_SNAP_PATH


def load_snap(path: Path | None = None) -> dict[str, Any]:
    p = snap_path(path)
    try:
        with p.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {"layout": "2x2", "win_z": True, "electric": True}
    layout = str(data.get("layout", "2x2"))
    if layout not in ("2x2", "3col", "off"):
        layout = "2x2"
    return {
        "layout": layout,
        "win_z": bool(data.get("win_z", True)),
        "electric": bool(data.get("electric", True)),
    }


def save_snap(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = snap_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Kyth window snap — Win+Arrow, offline\n",
        f'layout = "{cfg.get("layout", "2x2")}"',
        f"win_z = {str(bool(cfg.get('win_z', True))).lower()}",
        f"electric = {str(bool(cfg.get('electric', True))).lower()}",
    ]
    _atomic_write_text(p, "\n".join(lines) + "\n", encoding="utf-8")
    return p


def _kwriteconfig_bin() -> str | None:
    return shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5") or shutil.which("kwriteconfig")


def apply_snap(cfg: dict[str, Any] | None = None) -> list[str]:
    if cfg is None:
        cfg = load_snap()
    applied: list[str] = []
    bin_name = _kwriteconfig_bin()
    if not bin_name:
        logger.debug("kwriteconfig not found; window snap skipped")
        return applied

    try:
        res = run(
            [
                bin_name,
                "--file",
                "kwinrc",
                "--group",
                "Windows",
                "--key",
                "ElectricBorder",
                "--type",
                "bool",
                str(bool(cfg.get("electric", True))).lower(),
            ],
            capture_output=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0:
            applied.append("kwinrc ElectricBorder")
    except (OSError, ValueError, RuntimeError, KeyError):
        logger.debug("ElectricBorder write failed", exc_info=True)

    # Win+Arrow shortcuts via kglobalshortcutsrc (best-effort).
    for act, key in (
        ("Window Quick Tile Left", "Meta+Left"),
        ("Window Quick Tile Right", "Meta+Right"),
        ("Window Maximize", "Meta+Up"),
    ):
        try:
            run(
                [
                    bin_name,
                    "--file",
                    "kglobalshortcutsrc",
                    "--group",
                    "kwin",
                    "--key",
                    act,
                    f"{key},none,{act}",
                ],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (OSError, ValueError, RuntimeError, KeyError):
            logger.debug("shortcut write failed for %s", act, exc_info=True)

    try:
        import time

        _atomic_write_text(Path("/run/kyth-snap-ttl"), str(int(time.time()) + 30), encoding="utf-8")
    except (OSError, ValueError, RuntimeError):
        logger.debug("snap ttl write failed", exc_info=True)
    return applied
