"""Bore tunables — bore.toml, kernel.sched_bore."""
from __future__ import annotations
import os, tomllib
from pathlib import Path
from typing import Any
DEFAULT_BORE_PATH=Path("/etc/kyth/bore.toml")
DEFAULT_CONF=Path("/etc/sysctl.d/99-kyth-bore.conf")
def bore_config_path(path: Path|None=None) -> Path:
    if path is not None: return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1": return Path(xdg)/"kyth"/"bore.toml"
    return DEFAULT_BORE_PATH
def load_bore(path: Path|None=None) -> dict[str,Any]:
    p=bore_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError): return {"profile":"balanced"}
    prof=str(data.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    return {"profile":prof}
def save_bore(cfg: dict[str,Any], path: Path|None=None) -> Path:
    p=bore_config_path(path); p.parent.mkdir(parents=True, exist_ok=True)
    prof=str(cfg.get("profile","balanced")).lower()
    if prof not in ("balanced","gaming"): prof="balanced"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(f"# Kyth Bore — offline\nprofile = \"{prof}\"\n", encoding="utf-8")
    tmp.replace(p)
    return p
def generate_bore(cfg: dict[str,Any]|None=None, dest: Path|None=None) -> Path|None:
    if cfg is None: cfg=load_bore()
    dest=dest or DEFAULT_CONF
    if str(cfg.get("profile","balanced"))!="gaming":
        try: dest.exists() and dest.unlink()
        except OSError: pass
        return None
    # If SCX is active (scx_rusty), do not stack BORE — arbiter is single-writer.
    try:
        from .sched_arbiter import detect_scx_active as _detect_scx  # noqa: WPS433 -- local import to avoid cycle

        if _detect_scx():
            try: dest.exists() and dest.unlink()
            except OSError: pass
            return None
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort SCX probe
        pass
    content="# Kyth Bore gaming — generated\nkernel.sched_bore=1\nkernel.sched_bore_burst_penalty_offset=12\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp=dest.with_suffix(".tmp"); tmp.write_text(content,encoding="utf-8"); tmp.replace(dest); return dest
def bore_status(conf: Path=DEFAULT_CONF) -> str: return "gaming" if conf.exists() else "balanced"
