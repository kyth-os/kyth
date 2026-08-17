"""Locale + IME preset — locale.toml, offline."""
from __future__ import annotations
import logging

import os, tomllib
from pathlib import Path
from typing import Any
from kyth_shared.commands import run

logger = logging.getLogger(__name__)

DEFAULT_LOCALE_PATH = Path("/etc/kyth/locale.toml")

def locale_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1":
        return Path(xdg)/"kyth"/"locale.toml"
    return DEFAULT_LOCALE_PATH

def load_locale(path: Path | None = None) -> dict[str, Any]:
    p=locale_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"lang": "en_US.UTF-8", "ime": "fcitx5", "keymap": "us"}
    return {"lang": str(data.get("lang","en_US.UTF-8")), "ime": str(data.get("ime","fcitx5")) if str(data.get("ime","fcitx5")) in ("fcitx5","ibus","none") else "fcitx5", "keymap": str(data.get("keymap","us"))}

def save_locale(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=locale_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth locale + IME preset\n"]
    lines.append(f'lang = "{cfg.get("lang","en_US.UTF-8")}"')
    lines.append(f'ime = "{cfg.get("ime","fcitx5")}"')
    lines.append(f'keymap = "{cfg.get("keymap","us")}"')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p

def apply_locale(cfg: dict[str, Any] | None = None) -> list[str]:
    if cfg is None:
        cfg=load_locale()
    applied=[]
    try:
        run(["localectl","set-locale", f"LANG={cfg['lang']}"], capture_output=True, timeout=5)
        applied.append(f"LANG={cfg['lang']}")
    except Exception:
        logger.debug("handled expected exception", exc_info=True)
        pass
    if cfg["ime"]!="none":
        try:
            run(["kwriteconfig5","--file","kcminputrc","--group","Input","--key","ime", cfg["ime"]], capture_output=True, timeout=5)
        except Exception:
            logger.debug("handled expected exception", exc_info=True)
            pass
    return applied
