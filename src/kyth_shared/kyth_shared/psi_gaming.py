"""PSI gaming — psi.toml, gaming.slice MemoryHigh 90% vs 50%."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_PSI_PATH = Path("/etc/kyth/psi.toml")
DEFAULT_DROPIN = Path("/etc/systemd/system/gaming.slice.d/99-kyth-psi.conf")


def psi_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1":
        return Path(xdg)/"kyth"/"psi.toml"
    return DEFAULT_PSI_PATH


def load_psi(path: Path | None = None) -> dict[str,Any]:
    p=psi_config_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile":"balanced"}
    prof=str(data.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"):
        prof="balanced"
    return {"profile": prof}


def save_psi(cfg: dict[str,Any], path: Path | None = None) -> Path:
    p=psi_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof=str(cfg.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"):
        prof="balanced"
    p.write_text(f"# Kyth PSI gaming — offline\nprofile = \"{prof}\"\n",encoding="utf-8")
    return p


def generate_psi(cfg: dict[str,Any]|None=None, dest: Path|None=None) -> Path|None:
    if cfg is None:
        cfg=load_psi()
    dest=dest or DEFAULT_DROPIN
    if str(cfg.get("profile","balanced"))!="gaming":
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None
    content="# Kyth PSI gaming — generated\n[Slice]\nMemoryHigh=90%\nManagedOOMPreference=avoid\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text(content,encoding="utf-8")
    tmp.replace(dest)
    return dest


def psi_status(dropin: Path=DEFAULT_DROPIN) -> str:
    return "gaming" if dropin.exists() else "balanced"
