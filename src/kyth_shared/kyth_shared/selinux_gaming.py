"""SELinux gaming — allow_execheap gated gaming vs balanced."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

from .commands import run

DEFAULT_SELINUX_GAMING_PATH = Path("/etc/kyth/selinux-gaming.toml")


def selinux_gaming_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "selinux-gaming.toml"
    return DEFAULT_SELINUX_GAMING_PATH


def load_selinux_gaming(path: Path | None = None) -> dict[str, Any]:
    p = selinux_gaming_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced", "allow_execheap": False}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    return {"profile": prof, "allow_execheap": bool(data.get("allow_execheap", prof == "gaming"))}


def save_selinux_gaming(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = selinux_gaming_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    ah = bool(cfg.get("allow_execheap", prof == "gaming"))
    p.write_text(f"# Kyth selinux gaming — offline\nprofile = \"{prof}\"\nallow_execheap = {str(ah).lower()}\n", encoding="utf-8")
    return p


def apply_selinux_gaming(cfg: dict[str, Any] | None = None) -> bool:
    if cfg is None:
        cfg = load_selinux_gaming()
    ah = bool(cfg.get("allow_execheap", False))
    # only if SELinux enabled
    try:
        if run(["selinuxenabled"], capture_output=True, timeout=3).returncode != 0:
            return False
    except Exception:
        return False
    val = "on" if ah else "off"
    try:
        run(["setsebool", "allow_execheap", val], capture_output=True, timeout=5)
        return True
    except Exception:
        return False
