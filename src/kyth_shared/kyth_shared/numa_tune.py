"""NUMA X3D — numa.toml, taskset cpuset CCD0."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_NUMA_PATH = Path("/etc/kyth/numa.toml")


def numa_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1":
        return Path(xdg)/"kyth"/"numa.toml"
    return DEFAULT_NUMA_PATH


def load_numa(path: Path | None = None) -> dict[str,Any]:
    p=numa_config_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile":"balanced","cpus":""}
    prof=str(data.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"):
        prof="balanced"
    cpus=str(data.get("cpus",""))
    if cpus and not all(ch in "0123456789,-" for ch in cpus):
        cpus=""
    return {"profile":prof,"cpus":cpus}


def save_numa(cfg: dict[str,Any], path: Path | None = None) -> Path:
    p=numa_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof=str(cfg.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"):
        prof="balanced"
    cpus=str(cfg.get("cpus",""))
    p.write_text(f"# Kyth NUMA X3D — offline\nprofile = \"{prof}\"\ncpus = \"{cpus}\"\n",encoding="utf-8")
    return p


def numa_cpus(cfg: dict[str,Any]|None=None) -> str:
    if cfg is None:
        cfg=load_numa()
    cpus=str(cfg.get("cpus",""))
    if cpus:
        return cpus
    if str(cfg.get("profile","balanced"))=="gaming":
        try:
            from .performance import get_amd_ccd0_cpus
            return get_amd_ccd0_cpus() or ""
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            return ""
    return ""
