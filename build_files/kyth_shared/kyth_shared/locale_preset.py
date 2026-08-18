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
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return {"lang": "en_US.UTF-8", "ime": "fcitx5", "keymap": "us"}
    return {"lang": str(data.get("lang","en_US.UTF-8")), "ime": str(data.get("ime","fcitx5")) if str(data.get("ime","fcitx5")) in ("fcitx5","ibus","none") else "fcitx5", "keymap": str(data.get("keymap","us"))}

def save_locale(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=locale_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth locale + IME preset\n"]
    lines.append(f'lang = "{cfg.get("lang","en_US.UTF-8")}"')
    lines.append(f'ime = "{cfg.get("ime","fcitx5")}"')
    lines.append(f'keymap = "{cfg.get("keymap","us")}"')
    import tempfile

    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=f".{p.name}.")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
            f.flush()
            os.fsync(f.fileno())
        Path(tmp).replace(p)
        try:
            dfd = os.open(str(p.parent), os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except (OSError, ValueError):
            pass
    except BaseException:
        try:
            Path(tmp).unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
        raise
    return p

def apply_locale(cfg: dict[str, Any] | None = None) -> list[str]:
    if cfg is None:
        cfg=load_locale()
    applied=[]
    try:
        run(["localectl","set-locale", f"LANG={cfg['lang']}"], capture_output=True, timeout=5)
        applied.append(f"LANG={cfg['lang']}")
    except (OSError, ValueError) as exc:
        logger.debug("apply_locale localectl failed: %s", exc, exc_info=True)
        pass
    if cfg["ime"]!="none":
        try:
            run(["kwriteconfig5","--file","kcminputrc","--group","Input","--key","ime", cfg["ime"]], capture_output=True, timeout=5)
        except (OSError, ValueError) as exc:
            logger.debug("apply_locale ime failed: %s", exc, exc_info=True)
            pass
    return applied
