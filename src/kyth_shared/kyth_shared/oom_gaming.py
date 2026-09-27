"""OOM gaming — oom-gaming.toml, gaming.slice 75% vs desktop 50%."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_OOM_GAMING_PATH = Path("/etc/kyth/oom-gaming.toml")
DEFAULT_DROPIN = Path("/etc/systemd/system/gaming.slice.d/99-kyth-oom.conf")


def oom_gaming_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "oom-gaming.toml"
    return DEFAULT_OOM_GAMING_PATH


def load_oom_gaming(path: Path | None = None) -> dict[str, Any]:
    p = oom_gaming_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced", "limit": "50%"}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    lim = str(data.get("limit", "75%" if prof == "gaming" else "50%"))
    if not lim.endswith("%"):
        lim = "50%"
    return {"profile": prof, "limit": lim}


def save_oom_gaming(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = oom_gaming_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    lim = str(cfg.get("limit", "75%" if prof == "gaming" else "50%"))
    p.write_text(f"# Kyth OOM gaming — offline\nprofile = \"{prof}\"\nlimit = \"{lim}\"\n", encoding="utf-8")
    return p


def generate_oom_gaming(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_oom_gaming()
    dest = dest or DEFAULT_DROPIN
    if str(cfg.get("profile", "balanced")) != "gaming":
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None
    lim = str(cfg.get("limit", "75%"))
    content = f"# Kyth OOM gaming — generated\n[Unit]\nManagedOOMMemoryPressureLimit={lim}\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    return dest


def oom_gaming_status(dropin: Path = DEFAULT_DROPIN) -> str:
    return "gaming" if dropin.exists() else "balanced"
