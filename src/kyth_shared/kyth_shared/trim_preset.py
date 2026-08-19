"""Trim — trim.toml declarative, offline.

Continuous discard=async stalls QLC; use periodic fstrim weekly instead.
kyth enables nodiscard + ensures fstrim.timer active; balanced leaves defaults.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_TRIM_PATH = Path("/etc/kyth/trim.toml")


def trim_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "trim.toml"
    return DEFAULT_TRIM_PATH


def load_trim(path: Path | None = None) -> dict[str, Any]:
    p = trim_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced", "weekly": True}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in ("balanced", "kyth"):
        prof = "balanced"
    return {"profile": prof, "weekly": bool(data.get("weekly", True))}


def save_trim(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = trim_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "kyth"):
        prof = "balanced"
    wk = bool(cfg.get("weekly", True))
    lines = ["# Kyth trim — offline\n", f'profile = "{prof}"\n', f"weekly = {str(wk).lower()}\n"]
    p.write_text("".join(lines), encoding="utf-8")
    return p


def generate_trim_state(cfg: dict[str, Any] | None = None, marker: Path | None = None) -> Path | None:
    """Write marker for sysadmin audit; real nodiscard needs fstab edit (requires reboot).
    Helper writes marker and suggests fstab edit, enables timer when kyth.
    """
    if cfg is None:
        cfg = load_trim()
    marker = marker or Path("/run/kyth-trim-profile")
    if str(cfg.get("profile", "balanced")) != "kyth":
        try:
            if marker.exists():
                marker.unlink()
        except OSError:
            pass
        return None
    marker.parent.mkdir(parents=True, exist_ok=True)
    tmp = marker.with_suffix(".tmp")
    tmp.write_text("kyth-nodiscard,weekly\n", encoding="utf-8")
    tmp.replace(marker)
    return marker


def trim_status(marker: Path = Path("/run/kyth-trim-profile")) -> str:
    return "kyth" if marker.exists() else "balanced"
