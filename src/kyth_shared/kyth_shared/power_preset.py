"""Power tuned — power.toml governor/epp per profile, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path

DEFAULT_POWER_TUNED_PATH = Path("/etc/kyth/power.toml")

def power_tuned_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1":
        return Path(xdg)/"kyth"/"power.toml"
    return DEFAULT_POWER_TUNED_PATH

def load_power(path: Path | None = None) -> dict[str, dict[str, str]]:
    p=power_tuned_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"balanced": {"governor":"schedutil","epp":"balance_performance"}, "powersave": {"governor":"powersave","epp":"power"}}
    out={}
    for prof, e in data.get("profiles", {}).items() if isinstance(data.get("profiles"), dict) else []:
        if not isinstance(e, dict):
            continue
        out[str(prof)]={"governor": str(e.get("governor","schedutil")), "epp": str(e.get("epp","balance_performance"))}
    if not out:
        out={"balanced": {"governor":"schedutil","epp":"balance_performance"}, "powersave": {"governor":"powersave","epp":"power"}}
    return out

def save_power(profiles: dict[str, dict[str, str]], path: Path | None = None) -> Path:
    p=power_tuned_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth power tuned per profile, offline\n"]
    for prof in sorted(profiles):
        lines.append(f'[profiles."{prof}"]')
        lines.append(f'governor = "{profiles[prof].get("governor","schedutil")}"')
        lines.append(f'epp = "{profiles[prof].get("epp","balance_performance")}"')
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p
