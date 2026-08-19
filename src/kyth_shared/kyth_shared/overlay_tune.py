"""Overlay metacopy — podman-overlay.toml, metacopy=on for btrfs."""
from __future__ import annotations
import os, tomllib
from pathlib import Path
from typing import Any
DEFAULT_OVERLAY_PATH=Path("/etc/kyth/podman-overlay.toml")
DEFAULT_CONF=Path("/etc/containers/storage.conf.d/99-kyth-overlay.conf")
def overlay_config_path(path: Path|None=None) -> Path:
    if path is not None: return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1": return Path(xdg)/"kyth"/"podman-overlay.toml"
    return DEFAULT_OVERLAY_PATH
def load_overlay(path: Path|None=None) -> dict[str,Any]:
    p=overlay_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, ValueError, tomllib.TOMLDecodeError): return {"metacopy":"auto"}
    v=str(data.get("metacopy","auto")).lower()
    if v not in ("auto","on","off"): v="auto"
    return {"metacopy":v}
def save_overlay(cfg: dict[str,Any], path: Path|None=None) -> Path:
    p=overlay_config_path(path); p.parent.mkdir(parents=True, exist_ok=True)
    v=str(cfg.get("metacopy","auto")).lower()
    import tempfile

    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=f".{p.name}.")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(f"# Kyth overlay — offline\nmetacopy = \"{v}\"\n")
            f.flush()
            os.fsync(f.fileno())
        Path(tmp).replace(p)
        try:
            dfd = os.open(str(p.parent), os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except (OSError, ValueError):
            pass
    except BaseException:
        try:
            Path(tmp).unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
        raise
    return p
def _on_btrfs() -> bool:
    try:
        from .commands import run
        r=run(["findmnt","-no","FSTYPE","-T","/var"],capture_output=True,text=True,timeout=5)
        return bool(r and "btrfs" in r.stdout)
    except (OSError, ValueError): return False
def generate_overlay(cfg: dict[str,Any]|None=None, dest: Path|None=None) -> Path|None:
    if cfg is None: cfg=load_overlay()
    v=str(cfg.get("metacopy","auto"))
    if v=="auto": v="on" if _on_btrfs() else "off"
    dest=dest or DEFAULT_CONF
    if v=="off":
        try: dest.exists() and dest.unlink()
        except (OSError, ValueError): pass
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    import tempfile as _tf

    _fd, _tmp = _tf.mkstemp(dir=str(dest.parent), prefix=f".{dest.name}.")
    try:
        with open(_fd, "w", encoding="utf-8") as _f:
            _f.write('# Kyth overlay metacopy — generated\n[storage.options.overlay]\nmountopt = "metacopy=on"\n')
            _f.flush()
            os.fsync(_f.fileno())
        Path(_tmp).replace(dest)
        try:
            _dfd = os.open(str(dest.parent), os.O_DIRECTORY)
            try:
                os.fsync(_dfd)
            finally:
                os.close(_dfd)
        except (OSError, ValueError):
            pass
    except BaseException:
        try:
            Path(_tmp).unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
        raise
    return dest
