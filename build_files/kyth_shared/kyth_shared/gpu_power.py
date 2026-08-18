"""GPU power — gpu-power.toml declarative, offline.

Gaming → DPM high + power profile, balanced → auto. No daemon.
"""
from __future__ import annotations

import os
import tempfile
import tomllib
from pathlib import Path
from typing import Any


def _atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with open(fd, "w", encoding=encoding) as f:
            f.write(content)
        Path(tmp).replace(path)
    except BaseException:
        try:
            Path(tmp).unlink(missing_ok=True)
        except Exception:
            pass
        raise

DEFAULT_GPU_POWER_PATH = Path("/etc/kyth/gpu-power.toml")


def gpu_power_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "gpu-power.toml"
    return DEFAULT_GPU_POWER_PATH


def load_gpu_power(path: Path | None = None) -> dict[str, Any]:
    p = gpu_power_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced", "dpm": "auto"}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in ("balanced", "kyth"):
        prof = "balanced"
    dpm = str(data.get("dpm", "auto"))
    if dpm not in ("auto", "high", "low"):
        dpm = "auto"
    return {"profile": prof, "dpm": dpm}


def save_gpu_power(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = gpu_power_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "kyth"):
        prof = "balanced"
    dpm = str(cfg.get("dpm", "auto"))
    lines = ["# Kyth GPU power — offline\n", f'profile = "{prof}"\n', f'dpm = "{dpm}"\n']
    _atomic_write_text(p, "".join(lines), encoding="utf-8")
    return p


def apply_gpu_power(cfg: dict[str, Any] | None = None) -> bool:
    if cfg is None:
        cfg = load_gpu_power()
    prof = str(cfg.get("profile", "balanced"))
    # map kyth → high, balanced → auto
    target = cfg.get("dpm", "high" if prof == "kyth" else "auto")
    ok = False
    for g in Path("/sys/class/drm").glob("card*/device/power_dpm_force_performance_level"):
        try:
            g.write_text(target, encoding="utf-8")
            ok = True
        except OSError:
            pass
    # also try pp_power_profile_mode via copy?
    return ok


def gpu_power_status() -> str:
    cfg = load_gpu_power()
    return str(cfg.get("profile", "balanced"))
