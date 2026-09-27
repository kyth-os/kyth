"""THP collapse — thp-collapse.toml, defrag 0 gaming vs 1 desktop."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_THP_COLLAPSE_PATH = Path("/etc/kyth/thp-collapse.toml")
DEFAULT_CONF = Path("/etc/sysctl.d/99-kyth-thp-collapse.conf")


def thp_collapse_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1":
        return Path(xdg)/"kyth"/"thp-collapse.toml"
    return DEFAULT_THP_COLLAPSE_PATH


def load_thp_collapse(path: Path | None = None) -> dict[str,Any]:
    p=thp_collapse_config_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile":"balanced"}
    prof=str(data.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"):
        prof="balanced"
    return {"profile":prof}


def save_thp_collapse(cfg: dict[str,Any], path: Path | None = None) -> Path:
    p=thp_collapse_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof=str(cfg.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"):
        prof="balanced"
    p.write_text(f"# Kyth THP collapse — offline\nprofile = \"{prof}\"\n",encoding="utf-8")
    return p


def generate_thp_collapse(cfg: dict[str,Any]|None=None, dest: Path|None=None) -> Path|None:
    if cfg is None:
        cfg=load_thp_collapse()
    dest=dest or DEFAULT_CONF
    if str(cfg.get("profile","balanced"))!="gaming":
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None
    content="# Kyth THP collapse gaming — generated\nkernel.khugepaged_defrag=0\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text(content,encoding="utf-8")
    tmp.replace(dest)
    return dest


def thp_collapse_status(conf: Path=DEFAULT_CONF) -> str:
    return "gaming" if conf.exists() else "balanced"
