"""Flatpak prefetch — flatpak-prefetch.toml, timer daily prefetch."""
from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_text as _atomic_write_text

_logger = logging.getLogger(__name__)


DEFAULT_FLATPAK_PREFETCH_PATH = Path("/etc/kyth/flatpak-prefetch.toml")
DEFAULT_TIMER_DROPIN = Path("/etc/systemd/system/flatpak-prefetch.timer.d/99-kyth.conf")
DEFAULT_SERVICE = Path("/etc/systemd/system/flatpak-prefetch.service")


def flatpak_prefetch_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "flatpak-prefetch.toml"
    return DEFAULT_FLATPAK_PREFETCH_PATH


def load_flatpak_prefetch(path: Path | None = None) -> dict[str, Any]:
    p = flatpak_prefetch_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        _logger.debug("load_flatpak_prefetch failed for %s: %s", p, exc, exc_info=True)
        return {"enabled": False, "time": "02:00"}
    en = bool(data.get("enabled", False))
    t = str(data.get("time", "02:00"))
    if ":" not in t or len(t) > 5:
        t = "02:00"
    return {"enabled": en, "time": t}


def save_flatpak_prefetch(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = flatpak_prefetch_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    en = bool(cfg.get("enabled", False))
    t = str(cfg.get("time", "02:00"))
    try:
        _atomic_write_text(p, f"# Kyth flatpak prefetch — offline\nenabled = {str(en).lower()}\ntime = \"{t}\"\n")
    except (OSError, ValueError) as exc:
        _logger.debug("save_flatpak_prefetch failed for %s: %s", p, exc, exc_info=True)
        raise
    return p


def generate_flatpak_prefetch(cfg: dict[str, Any] | None = None, service: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_flatpak_prefetch()
    service = service or DEFAULT_SERVICE
    if not cfg.get("enabled"):
        for d in (service, DEFAULT_TIMER_DROPIN):
            try:
                if d.exists():
                    d.unlink()
            except OSError as exc:
                _logger.debug("flatpak prefetch cleanup failed for %s: %s", d, exc, exc_info=True)
        return None
    t = str(cfg.get("time", "02:00"))
    service.parent.mkdir(parents=True, exist_ok=True)
    try:
        _atomic_write_text(
            service,
            f"""[Unit]
Description=Kyth flatpak prefetch — off-peak
[Service]
Type=oneshot
ExecStart=/usr/bin/flatpak update --no-deploy -y
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
""",
        )
    except (OSError, ValueError) as exc:
        _logger.debug("generate_flatpak_prefetch service failed: %s", exc, exc_info=True)
        raise
    timer = Path("/etc/systemd/system/flatpak-prefetch.timer")
    timer.parent.mkdir(parents=True, exist_ok=True)
    hour, minute = (t.split(":") + ["00"])[:2]
    try:
        _atomic_write_text(
            timer,
            f"""[Unit]
Description=Kyth flatpak prefetch timer
[Timer]
OnCalendar=*-*-* {hour}:{minute}:00
Persistent=true
[Install]
WantedBy=timers.target
""",
        )
    except (OSError, ValueError) as exc:
        _logger.debug("generate_flatpak_prefetch timer failed: %s", exc, exc_info=True)
        raise
    return service


def flatpak_prefetch_status(service: Path = DEFAULT_SERVICE) -> str:
    return "enabled" if service.exists() else "off"
