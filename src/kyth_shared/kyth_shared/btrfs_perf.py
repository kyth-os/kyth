"""Btrfs perf — btrfs-perf.toml declarative, offline.

Adds compress-force=zstd:1,noatime when enabled. Revert removes drop-in.
Hash-gated, does not bake mount opts into image.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_BTRFS_PERF_PATH = Path("/etc/kyth/btrfs-perf.toml")
DEFAULT_DROPIN = Path("/etc/systemd/system/-.mount.d/99-kyth-btrfs.conf")
# also handle var mount
VAR_DROPIN = Path("/etc/systemd/system/var.mount.d/99-kyth-btrfs.conf")


def btrfs_perf_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "btrfs-perf.toml"
    return DEFAULT_BTRFS_PERF_PATH


def load_btrfs_perf(path: Path | None = None) -> dict[str, Any]:
    p = btrfs_perf_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return {"profile": "balanced", "compress": "zstd:1"}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in ("balanced", "kyth"):
        prof = "balanced"
    comp = str(data.get("compress", "zstd:1"))
    if comp not in ("zstd:1", "zstd:3", "zstd", "lzo", "off"):
        comp = "zstd:1"
    return {"profile": prof, "compress": comp}


def save_btrfs_perf(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = btrfs_perf_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "kyth"):
        prof = "balanced"
    comp = str(cfg.get("compress", "zstd:1"))
    lines = ["# Kyth btrfs perf — offline\n", f'profile = "{prof}"\n', f'compress = "{comp}"\n']
    import tempfile

    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=f".{p.name}.")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write("".join(lines))
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


def _btrfs_opts(compress: str) -> str:
    if compress == "off":
        return "noatime,space_cache=v2,commit=120"
    if compress == "zstd":
        compress = "zstd:1"
    c = f"compress-force={compress}" if compress != "off" else ""
    parts = [c, "noatime", "space_cache=v2", "commit=120"]
    return ",".join(p for p in parts if p)


def generate_btrfs_dropin(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_btrfs_perf()
    dest = dest or DEFAULT_DROPIN
    custom = dest != DEFAULT_DROPIN
    if str(cfg.get("profile", "balanced")) != "kyth":
        targets = (dest,) if custom else (dest, VAR_DROPIN)
        for d in targets:
            try:
                if d.exists():
                    d.unlink()
            except (OSError, ValueError):
                pass
        return None
    opts = _btrfs_opts(str(cfg.get("compress", "zstd:1")))
    content = f"# Kyth btrfs perf — generated\n[Mount]\nOptions={opts}\n"
    targets = (dest,) if custom else (dest, VAR_DROPIN)
    for d in targets:
        try:
            d.parent.mkdir(parents=True, exist_ok=True)
            import tempfile as _tf

            _fd, _tmp = _tf.mkstemp(dir=str(d.parent), prefix=f".{d.name}.")
            with open(_fd, "w", encoding="utf-8") as _f:
                _f.write(content)
                _f.flush()
                os.fsync(_f.fileno())
            Path(_tmp).replace(d)
            try:
                _dfd = os.open(str(d.parent), os.O_DIRECTORY)
                try:
                    os.fsync(_dfd)
                finally:
                    os.close(_dfd)
            except (OSError, ValueError):
                pass
        except (OSError, ValueError):
            pass
    return dest


def btrfs_perf_status(dropin: Path = DEFAULT_DROPIN) -> str:
    return "kyth" if dropin.exists() else "balanced"
