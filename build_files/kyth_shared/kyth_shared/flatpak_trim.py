"""Flatpak trim — flatpak-trim.toml, weekly unused removal."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_FLATPAK_TRIM_PATH = Path("/etc/kyth/flatpak-trim.toml")
DEFAULT_SERVICE = Path("/etc/systemd/system/kyth-flatpak-trim.service")
DEFAULT_TIMER = Path("/etc/systemd/system/kyth-flatpak-trim.timer")


def flatpak_trim_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "flatpak-trim.toml"
    return DEFAULT_FLATPAK_TRIM_PATH


def load_flatpak_trim(path: Path | None = None) -> dict[str, Any]:
    p = flatpak_trim_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"enabled": True}
    return {"enabled": bool(data.get("enabled", True))}


def save_flatpak_trim(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = flatpak_trim_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    en = bool(cfg.get("enabled", True))
    p.write_text(f"# Kyth flatpak trim — offline\nenabled = {str(en).lower()}\n", encoding="utf-8")
    return p


def generate_flatpak_trim(cfg: dict[str, Any] | None = None, service: Path | None = None, timer: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_flatpak_trim()
    service = service or DEFAULT_SERVICE
    timer = timer or DEFAULT_TIMER
    if not cfg.get("enabled"):
        for d in (service, timer):
            try:
                if d.exists():
                    d.unlink()
            except OSError:
                pass
        return None
    service.parent.mkdir(parents=True, exist_ok=True)
    service.write_text(
        "[Unit]\nDescription=Kyth flatpak trim — remove unused runtimes\n[Service]\nType=oneshot\nExecStart=/usr/bin/flatpak uninstall --unused -y --noninteractive\nNice=19\nIOSchedulingClass=best-effort\nIOSchedulingPriority=7\n",
        encoding="utf-8",
    )
    timer.parent.mkdir(parents=True, exist_ok=True)
    timer.write_text(
        "[Unit]\nDescription=Kyth flatpak trim timer\n[Timer]\nOnCalendar=weekly\nPersistent=true\n[Install]\nWantedBy=timers.target\n",
        encoding="utf-8",
    )
    return service


def flatpak_trim_status(service: Path = DEFAULT_SERVICE) -> str:
    return "enabled" if service.exists() else "off"


def validate_remotes(data) -> None:
    if not isinstance(data, list): raise ValueError("must be list")
    allowed={"name","title","url","subset"}
    for e in data:
        if not isinstance(e, dict): raise ValueError(f"bad {e!r}")
        unk=set(e)-allowed
        if unk: raise ValueError(f"unknown {unk}")
        if not e.get("name") or not e.get("url"): raise ValueError(f"missing name/url {e!r}")
        url=e["url"]
        if not url.startswith("https://") or not url.endswith(".flatpakrepo"): raise ValueError(f"bad url {url!r}")
