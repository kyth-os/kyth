"""CFS gaming burst — gaming-cfs.toml, gaming.slice CPUQuota 400% weight 800."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_GAMING_CFS_PATH = Path("/etc/kyth/gaming-cfs.toml")
DEFAULT_DROPIN = Path("/etc/systemd/system/gaming.slice.d/99-kyth-cfs.conf")


def gaming_cfs_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "gaming-cfs.toml"
    return DEFAULT_GAMING_CFS_PATH


def load_gaming_cfs(path: Path | None = None) -> dict[str, Any]:
    p = gaming_cfs_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced"}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    return {"profile": prof}


def save_gaming_cfs(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = gaming_cfs_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    p.write_text(f"# Kyth gaming CFS — offline\nprofile = \"{prof}\"\n", encoding="utf-8")
    return p


def generate_gaming_cfs(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_gaming_cfs()
    dest = dest or DEFAULT_DROPIN
    if str(cfg.get("profile", "balanced")) != "gaming":
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None
    content = "# Kyth gaming CFS burst — generated\n[Slice]\nCPUQuota=400%\nCPUWeight=800\nIOWeight=800\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    return dest


def gaming_cfs_status(dropin: Path = DEFAULT_DROPIN) -> str:
    return "gaming" if dropin.exists() else "balanced"
