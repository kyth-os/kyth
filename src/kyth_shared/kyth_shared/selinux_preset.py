"""SELinux preset — selinux.toml permissive+booleans, offline."""
from __future__ import annotations
import logging

import os, tomllib
from pathlib import Path
from typing import Any
from kyth_shared.commands import run

logger = logging.getLogger(__name__)

DEFAULT_SELINUX_PATH = Path("/etc/kyth/selinux.toml")

def selinux_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1":
        return Path(xdg)/"kyth"/"selinux.toml"
    return DEFAULT_SELINUX_PATH

def load_selinux(path: Path | None = None) -> dict[str, Any]:
    p=selinux_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"permissive": [], "booleans": {}}
    perm=data.get("permissive",[])
    if not isinstance(perm, list):
        perm=[]
    booleans=data.get("booleans",{})
    if not isinstance(booleans, dict):
        booleans={}
    return {"permissive": [str(x) for x in perm], "booleans": {str(k): bool(v) for k,v in booleans.items()}}

def save_selinux(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=selinux_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth SELinux preset, offline\n"]
    lines.append(f'permissive = {cfg.get("permissive",[])}')
    lines.append("[booleans]")
    for k,v in cfg.get("booleans", {}).items():
        lines.append(f'{k} = {str(bool(v)).lower()}')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p

def apply_selinux(cfg: dict[str, Any] | None = None) -> list[str]:
    if cfg is None:
        cfg=load_selinux()
    applied=[]
    if not Path("/usr/sbin/selinuxenabled").exists() and not Path("/usr/bin/selinuxenabled").exists():
        return applied
    try:
        if run(["selinuxenabled"], capture_output=True, timeout=3).returncode!=0:
            return applied
    except Exception:
        return applied
    for dom in cfg.get("permissive", []):
        try:
            run(["semanage","permissive","-a", dom], capture_output=True, timeout=5)
            applied.append(f"permissive:{dom}")
        except Exception:
            logger.debug("handled expected exception", exc_info=True)
            pass
    for k,v in cfg.get("booleans", {}).items():
        try:
            run(["setsebool","-P", k, "on" if v else "off"], capture_output=True, timeout=5)
            applied.append(f"boolean:{k}={v}")
        except Exception:
            logger.debug("handled expected exception", exc_info=True)
            pass
    return applied
