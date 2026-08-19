"""Sched latency — sched-latency.toml declarative, offline."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_SCHED_LATENCY_PATH = Path("/etc/kyth/sched-latency.toml")
DEFAULT_CONF = Path("/etc/sysctl.d/99-kyth-sched-latency.conf")


def sched_latency_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "sched-latency.toml"
    return DEFAULT_SCHED_LATENCY_PATH


def load_sched_latency(path: Path | None = None) -> dict[str, Any]:
    p = sched_latency_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced"}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in ("balanced", "kyth"):
        prof = "balanced"
    return {"profile": prof}


def save_sched_latency(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = sched_latency_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "kyth"):
        prof = "balanced"
    p.write_text(f"# Kyth sched latency — offline\nprofile = \"{prof}\"\n", encoding="utf-8")
    return p


def generate_sched_latency(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_sched_latency()
    dest = dest or DEFAULT_CONF
    if str(cfg.get("profile", "balanced")) != "kyth":
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None
    content = (
        "# Kyth sched latency — generated, gaming jitter cut\n"
        "kernel.sched_latency_ns = 6000000\n"
        "kernel.sched_min_granularity_ns = 1000000\n"
        "kernel.sched_wakeup_granularity_ns = 1000000\n"
        "kernel.sched_migration_cost_ns = 500000\n"
        "kernel.sched_nr_migrate = 32\n"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    return dest


def sched_latency_status(conf: Path = DEFAULT_CONF) -> str:
    return "kyth" if conf.exists() else "balanced"
