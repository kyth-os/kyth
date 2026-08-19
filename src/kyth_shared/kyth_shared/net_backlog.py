"""Net backlog — net-backlog.toml, gaming 5000 vs 1000."""
from __future__ import annotations
import os, tomllib
from pathlib import Path
from typing import Any
DEFAULT_BACKLOG_PATH=Path("/etc/kyth/net-backlog.toml")
DEFAULT_CONF=Path("/etc/sysctl.d/99-kyth-net-backlog.conf")
def backlog_config_path(path: Path|None=None) -> Path:
    if path is not None: return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1": return Path(xdg)/"kyth"/"net-backlog.toml"
    return DEFAULT_BACKLOG_PATH
def load_backlog(path: Path|None=None) -> dict[str,Any]:
    p=backlog_config_path(path)
    try: data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError): return {"profile":"balanced"}
    prof=str(data.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    return {"profile":prof}
def save_backlog(cfg: dict[str,Any], path: Path|None=None) -> Path:
    p=backlog_config_path(path); p.parent.mkdir(parents=True, exist_ok=True)
    prof=str(cfg.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    p.write_text(f"# Kyth net backlog — offline\nprofile = \"{prof}\"\n",encoding="utf-8"); return p
def generate_backlog(cfg: dict[str,Any]|None=None, dest: Path|None=None) -> Path|None:
    if cfg is None: cfg=load_backlog()
    dest=dest or DEFAULT_CONF
    if str(cfg.get("profile","balanced"))!="gaming":
        try: dest.exists() and dest.unlink()
        except OSError: pass
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text("# Kyth net backlog gaming — generated\nnet.core.netdev_max_backlog=5000\n",encoding="utf-8"); tmp.replace(dest); return dest
def backlog_status(conf: Path=DEFAULT_CONF) -> str: return "gaming" if conf.exists() else "balanced"
