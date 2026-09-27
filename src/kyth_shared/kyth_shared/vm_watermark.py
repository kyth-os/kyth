"""vm watermark — vm-watermark.toml, 500 gaming vs 10 balanced."""
from __future__ import annotations
import os, tomllib
from pathlib import Path
from typing import Any
DEFAULT_WATERMARK_PATH=Path("/etc/kyth/vm-watermark.toml")
DEFAULT_CONF=Path("/etc/sysctl.d/99-kyth-vm-watermark.conf")
def watermark_config_path(path: Path|None=None) -> Path:
    if path is not None: return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1": return Path(xdg)/"kyth"/"vm-watermark.toml"
    return DEFAULT_WATERMARK_PATH
def load_watermark(path: Path|None=None) -> dict[str,Any]:
    p=watermark_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError): return {"profile":"balanced"}
    prof=str(data.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    return {"profile":prof}
def save_watermark(cfg: dict[str,Any], path: Path|None=None) -> Path:
    p=watermark_config_path(path); p.parent.mkdir(parents=True, exist_ok=True)
    prof=str(cfg.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    p.write_text(f"# Kyth vm watermark — offline\nprofile = \"{prof}\"\n",encoding="utf-8"); return p
def generate_watermark(cfg: dict[str,Any]|None=None, dest: Path|None=None) -> Path|None:
    if cfg is None: cfg=load_watermark()
    dest=dest or DEFAULT_CONF
    if str(cfg.get("profile","balanced"))!="gaming":
        try: dest.exists() and dest.unlink()
        except OSError: pass
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text("# Kyth vm watermark gaming — generated\nvm.watermark_scale_factor=500\n",encoding="utf-8"); tmp.replace(dest); return dest
def watermark_status(conf: Path=DEFAULT_CONF) -> str: return "gaming" if conf.exists() else "balanced"
