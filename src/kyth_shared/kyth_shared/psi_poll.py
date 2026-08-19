"""PSI poll — psi-poll.toml, 500ms gaming vs 1000 desktop (shares profile helper with psi_gaming, cap-relief re-export pattern)."""
from __future__ import annotations
import os, tomllib
from pathlib import Path
from typing import Any
DEFAULT_PSI_POLL_PATH=Path("/etc/kyth/psi-poll.toml")
DEFAULT_CONF=Path("/etc/sysctl.d/99-kyth-psi-poll.conf")
def psi_poll_config_path(path: Path|None=None) -> Path:
    if path is not None: return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1": return Path(xdg)/"kyth"/"psi-poll.toml"
    return DEFAULT_PSI_POLL_PATH
def load_psi_poll(path: Path|None=None) -> dict[str,Any]:
    p=psi_poll_config_path(path)
    try: data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError): return {"profile":"balanced"}
    prof=str(data.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    return {"profile":prof}
def save_psi_poll(cfg: dict[str,Any], path: Path|None=None) -> Path:
    p=psi_poll_config_path(path); p.parent.mkdir(parents=True, exist_ok=True)
    prof=str(cfg.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    p.write_text(f"# Kyth PSI poll — offline\nprofile = \"{prof}\"\n",encoding="utf-8"); return p
def generate_psi_poll(cfg: dict[str,Any]|None=None, dest: Path|None=None) -> Path|None:
    if cfg is None: cfg=load_psi_poll()
    dest=dest or DEFAULT_CONF
    if str(cfg.get("profile","balanced"))!="gaming":
        try: dest.exists() and dest.unlink()
        except OSError: pass
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text("# Kyth PSI poll gaming — generated\nvm.pressure_poll=500\n",encoding="utf-8"); tmp.replace(dest); return dest
def psi_poll_status(conf: Path=DEFAULT_CONF) -> str: return "gaming" if conf.exists() else "balanced"
