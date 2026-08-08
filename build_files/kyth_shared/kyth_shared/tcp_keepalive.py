"""tcp keepalive — tcp-keepalive.toml, 120 gaming vs 7200."""
from __future__ import annotations
import os, tomllib
from pathlib import Path
from typing import Any
DEFAULT_PATH=Path("/etc/kyth/tcp-keepalive.toml")
DEFAULT_CONF=Path("/etc/sysctl.d/99-kyth-tcp-keepalive.conf")
def config_path(path: Path|None=None) -> Path:
    if path is not None: return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1": return Path(xdg)/"kyth"/"tcp-keepalive.toml"
    return DEFAULT_PATH
def load_tcp_keepalive(path: Path|None=None) -> dict[str,Any]:
    p=config_path(path)
    try: data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError): return {"profile":"balanced"}
    prof=str(data.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    return {"profile":prof}
def save_tcp_keepalive(cfg: dict[str,Any], path: Path|None=None) -> Path:
    p=config_path(path); p.parent.mkdir(parents=True, exist_ok=True)
    prof=str(cfg.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    p.write_text(f"# Kyth tcp keepalive — offline\nprofile = \"{prof}\"\n",encoding="utf-8"); return p
def generate_tcp_keepalive(cfg: dict[str,Any]|None=None, dest: Path|None=None) -> Path|None:
    if cfg is None: cfg=load_tcp_keepalive()
    dest=dest or DEFAULT_CONF
    if str(cfg.get("profile","balanced"))!="gaming":
        try: dest.exists() and dest.unlink()
        except: pass
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text("# Kyth tcp keepalive gaming — generated\nnet.ipv4.tcp_keepalive_time=120\n",encoding="utf-8"); tmp.replace(dest); return dest
def tcp_keepalive_status(conf: Path=DEFAULT_CONF) -> str: return "gaming" if conf.exists() else "balanced"
