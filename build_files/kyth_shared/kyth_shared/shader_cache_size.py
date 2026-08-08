"""Shader cache size — auto 2G <8GB VRAM else 4G."""
from __future__ import annotations
import os, tomllib, re
from pathlib import Path
from typing import Any
from .commands import run
DEFAULT_SHADER_SIZE_PATH=Path("/etc/kyth/shader-cache-size.toml")
DEFAULT_CONF=Path("/etc/environment.d/99-kyth-shader-size.conf")
def shader_size_config_path(path: Path|None=None) -> Path:
    if path is not None: return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1": return Path(xdg)/"kyth"/"shader-cache-size.toml"
    return DEFAULT_SHADER_SIZE_PATH
def load_shader_size(path: Path|None=None) -> dict[str,Any]:
    p=shader_size_config_path(path)
    try: data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError): return {"mode":"auto","size":"2G"}
    mode=str(data.get("mode","auto")).lower()
    if mode not in ("auto","manual"): mode="auto"
    size=str(data.get("size","2G"))
    if size not in ("1G","2G","4G","8G"): size="2G"
    return {"mode":mode,"size":size}
def save_shader_size(cfg: dict[str,Any], path: Path|None=None) -> Path:
    p=shader_size_config_path(path); p.parent.mkdir(parents=True, exist_ok=True)
    mode=str(cfg.get("mode","auto")).lower(); size=str(cfg.get("size","2G"))
    p.write_text(f"# Kyth shader cache size — offline\nmode = \"{mode}\"\nsize = \"{size}\"\n",encoding="utf-8"); return p
def _vram_gb() -> int:
    try:
        r=run(["lspci","-v"],capture_output=True,text=True,timeout=5)
        if r and r.stdout:
            m=re.search(r"VRAM.*?(\d+)G",r.stdout)
            if m: return int(m.group(1))
    except Exception: pass
    try:
        for d in Path("/sys/class/drm").glob("card*/device/mem_info_vram_total"):
            try: return int(d.read_text().strip())//1024//1024//1024
            except: pass
    except: pass
    return 8
def resolve_size(cfg: dict[str,Any]|None=None) -> str:
    if cfg is None: cfg=load_shader_size()
    if str(cfg.get("mode","auto"))=="manual": return str(cfg.get("size","2G"))
    return "4G" if _vram_gb()>=8 else "2G"
def generate_shader_size(cfg: dict[str,Any]|None=None, dest: Path|None=None) -> Path|None:
    if cfg is None: cfg=load_shader_size()
    sz=resolve_size(cfg)
    dest=dest or DEFAULT_CONF
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text(f"# Kyth shader cache size — generated\nMESA_SHADER_CACHE_MAX_SIZE={sz}\n__GL_SHADER_DISK_CACHE_SIZE={sz}\n",encoding="utf-8"); tmp.replace(dest); return dest
