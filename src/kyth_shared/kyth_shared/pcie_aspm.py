"""PCIe ASPM — pcie.toml, 61-kyth-pcie.rules L1 off for gaming."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_PCIE_PATH = Path("/etc/kyth/pcie.toml")
DEFAULT_RULE = Path("/etc/udev/rules.d/61-kyth-pcie.rules")


def pcie_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1":
        return Path(xdg)/"kyth"/"pcie.toml"
    return DEFAULT_PCIE_PATH


def load_pcie(path: Path | None = None) -> dict[str,Any]:
    p=pcie_config_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile":"balanced"}
    prof=str(data.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"):
        prof="balanced"
    return {"profile":prof}


def save_pcie(cfg: dict[str,Any], path: Path | None = None) -> Path:
    p=pcie_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof=str(cfg.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"):
        prof="balanced"
    p.write_text(f"# Kyth PCIe ASPM — offline\nprofile = \"{prof}\"\n",encoding="utf-8")
    return p


def generate_pcie(cfg: dict[str,Any]|None=None, dest: Path|None=None) -> Path|None:
    if cfg is None:
        cfg=load_pcie()
    dest=dest or DEFAULT_RULE
    if str(cfg.get("profile","balanced"))!="gaming":
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None
    content='# Kyth PCIe ASPM gaming — generated\nACTION=="add", SUBSYSTEM=="pci", ATTR{link/l1_aspm}="0"\n'
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text(content,encoding="utf-8")
    tmp.replace(dest)
    return dest


def pcie_status(rule: Path=DEFAULT_RULE) -> str:
    return "gaming" if rule.exists() else "balanced"
