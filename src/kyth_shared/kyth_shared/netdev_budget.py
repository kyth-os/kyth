"""netdev budget — netdev-budget.toml, 600 gaming."""
from __future__ import annotations
import os, tomllib
from pathlib import Path
from typing import Any
DEFAULT_PATH=Path("/etc/kyth/netdev-budget.toml")
DEFAULT_CONF=Path("/etc/sysctl.d/99-kyth-netdev-budget.conf")
def config_path(path: Path|None=None) -> Path:
    if path is not None: return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1": return Path(xdg)/"kyth"/"netdev-budget.toml"
    return DEFAULT_PATH
def load_netdev_budget(path: Path|None=None) -> dict[str,Any]:
    p=config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError): return {"profile":"balanced"}
    prof=str(data.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    return {"profile":prof}
def save_netdev_budget(cfg: dict[str,Any], path: Path|None=None) -> Path:
    p=config_path(path); p.parent.mkdir(parents=True, exist_ok=True)
    prof=str(cfg.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    p.write_text(f"# Kyth netdev budget — offline\nprofile = \"{prof}\"\n",encoding="utf-8"); return p
def generate_netdev_budget(cfg: dict[str,Any]|None=None, dest: Path|None=None) -> Path|None:
    if cfg is None: cfg=load_netdev_budget()
    dest=dest or DEFAULT_CONF
    if str(cfg.get("profile","balanced"))!="gaming":
        try: dest.exists() and dest.unlink()
        except OSError: pass
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text("# Kyth netdev budget gaming — generated\nnet.core.netdev_budget=600\n",encoding="utf-8"); tmp.replace(dest); return dest
def netdev_budget_status(conf: Path=DEFAULT_CONF) -> str: return "gaming" if conf.exists() else "balanced"
