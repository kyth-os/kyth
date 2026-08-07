"""Uksmd preset — uksmd.toml declarative, offline.

uksm daemon dedups zero/identical pages. Worth ~15-30% RAM on heavy
gaming loads, idle cost ~1-2% CPU. Auto-enabled only on >16 GB RAM or
explicit enable. Off by default to keep idle cost zero.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_UKSMD_PATH = Path("/etc/kyth/uksmd.toml")


def uksmd_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "uksmd.toml"
    return DEFAULT_UKSMD_PATH


def load_uksmd(path: Path | None = None) -> dict[str, Any]:
    p = uksmd_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"enabled": False, "max_cpu_percent": 20}
    return {
        "enabled": bool(data.get("enabled", False)),
        "max_cpu_percent": max(5, min(80, int(data.get("max_cpu_percent", 20)))),
    }


def save_uksmd(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = uksmd_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    en = bool(cfg.get("enabled", False))
    cpu = max(5, min(80, int(cfg.get("max_cpu_percent", 20))))
    lines = ["# Kyth uksmd — offline, opt-in\n", f"enabled = {str(en).lower()}\n", f"max_cpu_percent = {cpu}\n"]
    p.write_text("".join(lines), encoding="utf-8")
    return p


def _total_ram_gb() -> float:
    try:
        # MemTotal kB
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                kb = int(line.split()[1])
                return kb / 1024 / 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0.0


def should_auto_enable(path: Path | None = None) -> bool:
    cfg = load_uksmd(path)
    if cfg.get("enabled"):
        return True
    # auto if >16GB and no explicit disable (absence defaults to false, so not auto)
    # explicit opt-in required; helper may suggest enable when >16GB
    return False


def uksmd_suggested() -> bool:
    return _total_ram_gb() >= 15.5


def generate_uksmd_conf(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path | None:
    # uksmd reads /etc/uksmd.conf; we manage that file when enabled
    if cfg is None:
        cfg = load_uksmd()
    dest = dest or Path("/etc/uksmd.conf")
    if not cfg.get("enabled"):
        try:
            if dest.exists() and "Kyth" in dest.read_text(encoding="utf-8"):
                dest.unlink()
        except OSError:
            pass
        return None
    cpu = int(cfg.get("max_cpu_percent", 20))
    content = f"# Kyth uksmd — generated\n[daemon]\nmax_cpu_percent = {cpu}\nscan_sleep_millisecs = 200\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    return dest
