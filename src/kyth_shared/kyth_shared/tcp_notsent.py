"""tcp notsent — tcp-notsent.toml, 16384 gaming vs default."""
from __future__ import annotations
import os, tomllib
from pathlib import Path
from typing import Any
DEFAULT_TCP_NOTSENT_PATH=Path("/etc/kyth/tcp-notsent.toml")
DEFAULT_CONF=Path("/etc/sysctl.d/99-kyth-tcp-notsent.conf")
def tcp_notsent_config_path(path: Path|None=None) -> Path:
    if path is not None: return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1": return Path(xdg)/"kyth"/"tcp-notsent.toml"
    return DEFAULT_TCP_NOTSENT_PATH
def load_tcp_notsent(path: Path|None=None) -> dict[str,Any]:
    p=tcp_notsent_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError): return {"profile":"balanced"}
    prof=str(data.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    return {"profile":prof}
def save_tcp_notsent(cfg: dict[str,Any], path: Path|None=None) -> Path:
    p=tcp_notsent_config_path(path); p.parent.mkdir(parents=True, exist_ok=True)
    prof=str(cfg.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    p.write_text(f"# Kyth tcp notsent — offline\nprofile = \"{prof}\"\n",encoding="utf-8"); return p
def generate_tcp_notsent(cfg: dict[str,Any]|None=None, dest: Path|None=None) -> Path|None:
    if cfg is None: cfg=load_tcp_notsent()
    dest=dest or DEFAULT_CONF
    if str(cfg.get("profile","balanced"))!="gaming":
        try: dest.exists() and dest.unlink()
        except OSError: pass
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text("# Kyth tcp notsent gaming — generated\nnet.ipv4.tcp_notsent_lowat=16384\n",encoding="utf-8"); tmp.replace(dest); return dest
def tcp_notsent_status(conf: Path=DEFAULT_CONF) -> str: return "gaming" if conf.exists() else "balanced"
