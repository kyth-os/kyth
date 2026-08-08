"""dirty ratio — dirty-ratio.toml, 5/5 gaming vs defaults."""
from __future__ import annotations
import os, tomllib
from pathlib import Path
from typing import Any
DEFAULT_DIRTY_PATH=Path("/etc/kyth/dirty-ratio.toml")
DEFAULT_CONF=Path("/etc/sysctl.d/99-kyth-dirty-ratio.conf")
def dirty_ratio_config_path(path: Path|None=None) -> Path:
    if path is not None: return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1": return Path(xdg)/"kyth"/"dirty-ratio.toml"
    return DEFAULT_DIRTY_PATH
def load_dirty_ratio(path: Path|None=None) -> dict[str,Any]:
    p=dirty_ratio_config_path(path)
    try: data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError): return {"profile":"balanced"}
    prof=str(data.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    return {"profile":prof}
def save_dirty_ratio(cfg: dict[str,Any], path: Path|None=None) -> Path:
    p=dirty_ratio_config_path(path); p.parent.mkdir(parents=True, exist_ok=True)
    prof=str(cfg.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    p.write_text(f"# Kyth dirty ratio — offline\nprofile = \"{prof}\"\n",encoding="utf-8"); return p
def generate_dirty_ratio(cfg: dict[str,Any]|None=None, dest: Path|None=None) -> Path|None:
    if cfg is None: cfg=load_dirty_ratio()
    dest=dest or DEFAULT_CONF
    if str(cfg.get("profile","balanced"))!="gaming":
        try: dest.exists() and dest.unlink()
        except: pass
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text("# Kyth dirty ratio gaming — generated\nvm.dirty_ratio=5\nvm.dirty_background_ratio=5\nvm.dirty_writeback_centisecs=500\n",encoding="utf-8"); tmp.replace(dest); return dest
def dirty_ratio_status(conf: Path=DEFAULT_CONF) -> str: return "gaming" if conf.exists() else "balanced"
