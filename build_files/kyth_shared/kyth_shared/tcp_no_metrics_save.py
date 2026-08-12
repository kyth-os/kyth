"""tcp no metrics save — tcp-no-metrics-save.toml, 1 gaming."""
from __future__ import annotations
import os, tomllib
from pathlib import Path
from typing import Any
DEFAULT_PATH=Path("/etc/kyth/tcp-no-metrics-save.toml")
DEFAULT_CONF=Path("/etc/sysctl.d/99-kyth-tcp-no-metrics-save.conf")
def config_path(path: Path|None=None) -> Path:
    if path is not None: return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1": return Path(xdg)/"kyth"/"tcp-no-metrics-save.toml"
    return DEFAULT_PATH
def load_tcp_no_metrics_save(path: Path|None=None) -> dict[str,Any]:
    p=config_path(path)
    try: data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError): return {"profile":"balanced"}
    prof=str(data.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    return {"profile":prof}
def save_tcp_no_metrics_save(cfg: dict[str,Any], path: Path|None=None) -> Path:
    p=config_path(path); p.parent.mkdir(parents=True, exist_ok=True)
    prof=str(cfg.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    p.write_text(f"# Kyth tcp no metrics save — offline\nprofile = \"{prof}\"\n",encoding="utf-8"); return p
def generate_tcp_no_metrics_save(cfg: dict[str,Any]|None=None, dest: Path|None=None) -> Path|None:
    if cfg is None: cfg=load_tcp_no_metrics_save()
    dest=dest or DEFAULT_CONF
    if str(cfg.get("profile","balanced"))!="gaming":
        try: dest.exists() and dest.unlink()
        except OSError: pass
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text("# Kyth tcp no metrics save gaming — generated\nnet.ipv4.tcp_no_metrics_save=1\n",encoding="utf-8"); tmp.replace(dest); return dest
def tcp_no_metrics_save_status(conf: Path=DEFAULT_CONF) -> str: return "gaming" if conf.exists() else "balanced"
