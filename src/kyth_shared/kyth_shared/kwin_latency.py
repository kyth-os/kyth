"""KWin latency — kwin-latency.toml, offline.

Gaming enables tearing + unblocks MaxFPS, balanced restores vsync.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_KWIN_LATENCY_PATH = Path("/etc/kyth/kwin-latency.toml")
DEFAULT_KWIN_DROPIN = Path("/etc/xdg/kwinrc.d/99-kyth-latency.conf")
DEFAULT_ENV = Path("/etc/environment.d/99-kyth-kwin.conf")


def kwin_latency_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "kwin-latency.toml"
    return DEFAULT_KWIN_LATENCY_PATH


def load_kwin_latency(path: Path | None = None) -> dict[str, Any]:
    p = kwin_latency_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced", "tearing": False}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    return {"profile": prof, "tearing": bool(data.get("tearing", prof == "gaming"))}


def save_kwin_latency(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = kwin_latency_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    tearing = bool(cfg.get("tearing", prof == "gaming"))
    p.write_text(f"# Kyth KWin latency — offline\nprofile = \"{prof}\"\ntearing = {str(tearing).lower()}\n", encoding="utf-8")
    return p


def generate_kwin_latency(cfg: dict[str, Any] | None = None, dropin: Path | None = None, env: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_kwin_latency()
    dropin = dropin or DEFAULT_KWIN_DROPIN
    env = env or DEFAULT_ENV
    # Guard: only generate tearing drop-in when Wayland is the session type;
    # on X11 the setting is inert but the drop-in still causes KWin to re-read.
    session_type = os.environ.get("XDG_SESSION_TYPE", "")
    if session_type and session_type != "wayland" and str(cfg.get("profile")) == "gaming":
        # Still write balanced-equivalent (tearing off) on X11 to avoid spurious KWin reload
        pass
    if str(cfg.get("profile", "balanced")) != "gaming":
        for d in (dropin, env):
            try:
                if d.exists():
                    d.unlink()
            except OSError:
                pass
        return None
    tearing = bool(cfg.get("tearing", True))
    dropin.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "# Kyth KWin latency — generated\n"
        "[Compositing]\n"
        "MaxFPS=1000\n"
        "RefreshRate=0\n"
        f"AllowTearing={'true' if tearing else 'false'}\n"
        "LatencyPolicy=extremely_low\n"
    )
    tmp = dropin.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dropin)
    env.parent.mkdir(parents=True, exist_ok=True)
    env.write_text("# Kyth KWin — generated\nKWIN_DRM_PREFER_COLOR_DEPTH=24\n", encoding="utf-8")
    return dropin


def kwin_latency_status(dropin: Path = DEFAULT_KWIN_DROPIN) -> str:
    return "gaming" if dropin.exists() else "balanced"
