"""EPP per-AC — epp-ac.toml, performance on AC vs balanced on DC.

Single power owner is power-profiles-daemon (PPD); EPP only follows. The
generated udev rules therefore switch the PPD profile (performance on AC,
balanced on battery) and let PPD drive EPP itself — they never write
energy_performance_preference sysfs nodes directly, which would fight
kyth-power-arbiter, kyth-performance-mode, and PPD's own amd_pstate handling.
"""
from __future__ import annotations
import os, tomllib
from pathlib import Path
from typing import Any
DEFAULT_EPP_AC_PATH=Path("/etc/kyth/epp-ac.toml")
DEFAULT_RULE=Path("/etc/udev/rules.d/61-kyth-epp-ac.rules")
AC_PROFILE = "performance"
BATTERY_PROFILE = "balanced"
def epp_ac_config_path(path: Path|None=None) -> Path:
    if path is not None: return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1": return Path(xdg)/"kyth"/"epp-ac.toml"
    return DEFAULT_EPP_AC_PATH
def load_epp_ac(path: Path|None=None) -> dict[str,Any]:
    p=epp_ac_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError): return {"enabled":True}
    return {"enabled": bool(data.get("enabled",True))}
def save_epp_ac(cfg: dict[str,Any], path: Path|None=None) -> Path:
    p=epp_ac_config_path(path); p.parent.mkdir(parents=True, exist_ok=True)
    en=bool(cfg.get("enabled",True))
    tmp = p.with_suffix(".tmp")
    lines = ["# Kyth EPP AC — offline", f"enabled = {str(en).lower()}", ""]
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(p)
    return p
def generate_epp_ac(cfg: dict[str,Any]|None=None, dest: Path|None=None) -> Path|None:
    if cfg is None: cfg=load_epp_ac()
    dest=dest or DEFAULT_RULE
    if not cfg.get("enabled"):
        try: dest.exists() and dest.unlink()
        except OSError: pass
        return None
    lines = [
        "# Kyth EPP AC — generated: PPD profile follows AC state, EPP follows PPD",
        f'SUBSYSTEM=="power_supply", ATTR{{online}}=="1", RUN+="/usr/bin/powerprofilesctl set {AC_PROFILE}"',
        f'SUBSYSTEM=="power_supply", ATTR{{online}}=="0", RUN+="/usr/bin/powerprofilesctl set {BATTERY_PROFILE}"',
        "",
    ]
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8"); tmp.replace(dest); return dest
