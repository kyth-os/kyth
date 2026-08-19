"""THP tune — thp.toml declarative, offline.

MAdvise + khugepaged tuning cuts UE/Star Citizen stutter.
balanced leaves kernel defaults, kyth enables madvise + scan_sleep 10s.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_THP_PATH = Path("/etc/kyth/thp.toml")
DEFAULT_SYSCTL = Path("/etc/sysctl.d/99-kyth-thp.conf")
THP_ENABLED = Path("/sys/kernel/mm/transparent_hugepage/enabled")
THP_DEFRAG = Path("/sys/kernel/mm/transparent_hugepage/defrag")

VALID_PROFILES = {"balanced", "kyth"}


def thp_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "thp.toml"
    return DEFAULT_THP_PATH


def load_thp(path: Path | None = None) -> dict[str, Any]:
    p = thp_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced", "scan_sleep_ms": 10000}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in VALID_PROFILES:
        prof = "balanced"
    try:
        sl = int(data.get("scan_sleep_ms", 10000))
    except (TypeError, ValueError):
        sl = 10000
    sl = max(1000, min(60000, sl))
    return {"profile": prof, "scan_sleep_ms": sl}


def save_thp(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = thp_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in VALID_PROFILES:
        prof = "balanced"
    try:
        sl = int(cfg.get("scan_sleep_ms", 10000))
    except (TypeError, ValueError):
        sl = 10000
    sl = max(1000, min(60000, sl))
    lines = ["# Kyth THP — offline\n", f'profile = "{prof}"\n', f"scan_sleep_ms = {sl}\n"]
    p.write_text("".join(lines), encoding="utf-8")
    return p


def generate_thp_conf(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_thp()
    dest = dest or DEFAULT_SYSCTL
    if str(cfg.get("profile", "balanced")) != "kyth":
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None
    sl = int(cfg.get("scan_sleep_ms", 10000))
    content = (
        "# Kyth THP — generated\n"
        "vm.compaction_proactiveness = 0\n"
        f"kernel.khugepaged_scan_sleep_millisecs = {sl}\n"
        "kernel.khugepaged_alloc_sleep_millisecs = 60000\n"
        "kernel.khugepaged_max_ptes_none = 511\n"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    return dest


def thp_status(sysctl: Path = DEFAULT_SYSCTL) -> str:
    return "kyth" if sysctl.exists() else "balanced"
