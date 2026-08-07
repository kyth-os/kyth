"""min free kbytes — min-free-kbytes.toml, 131072 gaming."""
from __future__ import annotations
import os, tomllib
from pathlib import Path
from typing import Any
DEFAULT_PATH=Path("/etc/kyth/min-free-kbytes.toml")
DEFAULT_CONF=Path("/etc/sysctl.d/99-kyth-min-free-kbytes.conf")
def config_path(path: Path|None=None) -> Path:
    if path is not None: return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1": return Path(xdg)/"kyth"/"min-free-kbytes.toml"
    return DEFAULT_PATH
def load_min_free_kbytes(path: Path|None=None) -> dict[str,Any]:
    p=config_path(path)
    try: data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError): return {"profile":"balanced"}
    prof=str(data.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    return {"profile":prof}
def save_min_free_kbytes(cfg: dict[str,Any], path: Path|None=None) -> Path:
    p=config_path(path); p.parent.mkdir(parents=True, exist_ok=True)
    prof=str(cfg.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    p.write_text(f"# Kyth min free kbytes — offline\nprofile = \"{prof}\"\n",encoding="utf-8"); return p
def generate_min_free_kbytes(cfg: dict[str,Any]|None=None, dest: Path|None=None) -> Path|None:
    if cfg is None: cfg=load_min_free_kbytes()
    dest=dest or DEFAULT_CONF
    if str(cfg.get("profile","balanced"))!="gaming":
        try: dest.exists() and dest.unlink()
        except: pass
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text("# Kyth min free kbytes gaming — generated\nvm.min_free_kbytes=131072\n",encoding="utf-8"); tmp.replace(dest); return dest
def min_free_kbytes_status(conf: Path=DEFAULT_CONF) -> str: return "gaming" if conf.exists() else "balanced"
