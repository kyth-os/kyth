"""Privacy preset — privacy.toml geoclue/flatpak lockdown, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_PRIVACY_PATH = Path.home() / ".config" / "kyth" / "privacy.toml"

def privacy_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"privacy.toml"
    return DEFAULT_PRIVACY_PATH

def load_privacy(path: Path | None = None) -> dict[str, Any]:
    p=privacy_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"geoclue": False, "fingerprint": False, "telem_opt_out": True}
    return {"geoclue": bool(data.get("geoclue", False)), "fingerprint": bool(data.get("fingerprint", False)), "telem_opt_out": bool(data.get("telem_opt_out", True))}

def save_privacy(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=privacy_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth privacy preset, offline\n"]
    lines.append(f'geoclue = {str(bool(cfg.get("geoclue",False))).lower()}')
    lines.append(f'fingerprint = {str(bool(cfg.get("fingerprint",False))).lower()}')
    lines.append(f'telem_opt_out = {str(bool(cfg.get("telem_opt_out",True))).lower()}')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p
