"""Locale + IME preset — locale.toml, offline."""
from __future__ import annotations
import logging

import os, shutil, tomllib
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
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return {"lang": "en_US.UTF-8", "ime": "fcitx5", "keymap": "us", "timezone": ""}
    ime = str(data.get("ime","fcitx5"))
    if ime not in ("fcitx5","ibus","none"):
        ime = "fcitx5"
    return {"lang": str(data.get("lang","en_US.UTF-8")), "ime": ime, "keymap": str(data.get("keymap","us")), "timezone": str(data.get("timezone",""))}

def save_locale(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=locale_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth locale + IME preset\n"]
    lines.append(f'lang = "{cfg.get("lang","en_US.UTF-8")}"')
    lines.append(f'ime = "{cfg.get("ime","fcitx5")}"')
    lines.append(f'keymap = "{cfg.get("keymap","us")}"')
    lines.append(f'timezone = "{cfg.get("timezone","")}"')
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

def _kwriteconfig_bin() -> str | None:
    for name in ("kwriteconfig6", "kwriteconfig5", "kwriteconfig"):
        if shutil.which(name):
            return name
    return None

def _current_lang() -> str:
    """LANG from /etc/locale.conf, or '' when unset."""
    try:
        with open("/etc/locale.conf", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith("LANG="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""

def _current_timezone() -> str:
    """System timezone id, or '' when it cannot be determined."""
    try:
        res = run(["timedatectl", "show", "-p", "Timezone", "--value"], capture_output=True, timeout=5)
        zone = (res.stdout or "").strip()
        if zone:
            return zone
    except (OSError, ValueError) as exc:
        logger.debug("apply_locale timedatectl failed: %s", exc, exc_info=True)
    try:
        target = os.readlink("/etc/localtime")
        marker = "zoneinfo/"
        if marker in target:
            return target.split(marker, 1)[1]
    except OSError:
        pass
    return ""

def apply_locale(cfg: dict[str, Any] | None = None) -> list[str]:
    if cfg is None:
        cfg=load_locale()
    applied=[]
    # Seed-only: never override a LANG the installer or user already set.
    if not _current_lang():
        try:
            run(["localectl","set-locale", f"LANG={cfg['lang']}"], capture_output=True, timeout=5)
            applied.append(f"LANG={cfg['lang']}")
        except (OSError, ValueError) as exc:
            logger.debug("apply_locale localectl failed: %s", exc, exc_info=True)
            pass
    # First-boot timezone: only when the system is still on the default (UTC /
    # unknown) and the preset names a zone. Never re-point a configured system.
    want_tz = str(cfg.get("timezone", ""))
    if want_tz:
        current_tz = _current_timezone()
        if current_tz in ("", "UTC", "Etc/UTC"):
            try:
                run(["timedatectl", "set-timezone", want_tz], capture_output=True, timeout=10)
                applied.append(f"Timezone={want_tz}")
            except (OSError, ValueError) as exc:
                logger.debug("apply_locale timezone failed: %s", exc, exc_info=True)
                pass
    if cfg["ime"]!="none":
        writer = _kwriteconfig_bin()
        if writer:
            try:
                run([writer,"--file","kcminputrc","--group","Input","--key","ime", cfg["ime"]], capture_output=True, timeout=5)
                applied.append(f"ime={cfg['ime']}")
            except (OSError, ValueError) as exc:
                logger.debug("apply_locale ime failed: %s", exc, exc_info=True)
                pass
    return applied
