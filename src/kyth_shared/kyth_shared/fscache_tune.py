"""FSCache steam — fscache.toml, cachefilesd 10G."""
from __future__ import annotations
import os, tomllib
from pathlib import Path
from typing import Any
DEFAULT_FSCACHE_PATH=Path("/etc/kyth/fscache.toml")
DEFAULT_CONF=Path("/etc/cachefilesd.conf.d/99-kyth-fscache.conf")
DEFAULT_SERVICE=Path("/etc/systemd/system/cachefilesd.service.d/99-kyth.conf")
def fscache_config_path(path: Path|None=None) -> Path:
    if path is not None: return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1": return Path(xdg)/"kyth"/"fscache.toml"
    return DEFAULT_FSCACHE_PATH
def load_fscache(path: Path|None=None) -> dict[str,Any]:
    p=fscache_config_path(path)
    try: data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError): return {"enabled":False}
    return {"enabled": bool(data.get("enabled",False))}
def save_fscache(cfg: dict[str,Any], path: Path|None=None) -> Path:
    p=fscache_config_path(path); p.parent.mkdir(parents=True, exist_ok=True)
    en=bool(cfg.get("enabled",False))
    tmp = p.with_suffix(".tmp")
    tmp.write_text(f"# Kyth fscache — offline\nenabled = {str(en).lower()}\n", encoding="utf-8")
    tmp.replace(p)
    return p
def generate_fscache(cfg: dict[str,Any]|None=None, conf: Path|None=None) -> Path|None:
    if cfg is None: cfg=load_fscache()
    conf=conf or DEFAULT_CONF
    if not cfg.get("enabled"):
        try: conf.exists() and conf.unlink()
        except OSError: pass
        return None
    conf.parent.mkdir(parents=True, exist_ok=True)
    tmp=conf.with_suffix(".tmp")
    tmp.write_text("# Kyth fscache — generated\ndir /var/cache/fscache cachefiles:0x3f 10G\n",encoding="utf-8"); tmp.replace(conf); return conf
