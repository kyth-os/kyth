"""Ananicy gaming nice — ananicy.toml declarative, offline.

When profile=kyth writes 99-kyth-gaming.conf for ananicy-cpp:
gaming cgroup → nice -12 io realtime. Balanced removes.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_ANANICY_PATH = Path("/etc/kyth/ananicy.toml")
DEFAULT_RULE = Path("/etc/ananicy.d/99-kyth-gaming.conf")


def ananicy_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "ananicy.toml"
    return DEFAULT_ANANICY_PATH


def load_ananicy(path: Path | None = None) -> dict[str, Any]:
    p = ananicy_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced", "nice": -12, "ioclass": "realtime"}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in ("balanced", "kyth"):
        prof = "balanced"
    try:
        nice = int(data.get("nice", -12))
    except (TypeError, ValueError):
        nice = -12
    nice = max(-20, min(0, nice))
    ioc = str(data.get("ioclass", "realtime"))
    if ioc not in ("realtime", "best-effort", "idle"):
        ioc = "realtime"
    return {"profile": prof, "nice": nice, "ioclass": ioc}


def save_ananicy(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = ananicy_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "kyth"):
        prof = "balanced"
    try:
        nice = int(cfg.get("nice", -12))
    except (TypeError, ValueError):
        nice = -12
    nice = max(-20, min(0, nice))
    ioc = str(cfg.get("ioclass", "realtime"))
    lines = ["# Kyth ananicy — offline\n", f'profile = "{prof}"\n', f"nice = {nice}\n", f'ioclass = "{ioc}"\n']
    p.write_text("".join(lines), encoding="utf-8")
    return p


def generate_ananicy(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_ananicy()
    dest = dest or DEFAULT_RULE
    if str(cfg.get("profile", "balanced")) != "kyth":
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None
    nice = int(cfg.get("nice", -12))
    ioc = str(cfg.get("ioclass", "realtime"))
    # minimal ananicy-cpp rule: match gaming.slice cgroup
    content = (
        "# Kyth ananicy gaming — generated\n"
        '{"name":"gaming.slice","type":"cgroup","nice":' + str(nice) + ',"ioclass":"' + ioc + '","sched":"batch"}\n'
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    return dest


def ananicy_status(rule: Path = DEFAULT_RULE) -> str:
    return "kyth" if rule.exists() else "balanced"
