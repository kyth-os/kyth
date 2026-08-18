"""Battery health + charge limit — battery.toml, offline."""
from __future__ import annotations
import logging

import os, tomllib, json
from pathlib import Path
from typing import Any
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_BATTERY_PATH = Path.home() / ".config" / "kyth" / "battery.toml"
LEDGER_PATH = Path("/var/cache/kyth/battery.jsonl")

def battery_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"battery.toml"
    return DEFAULT_BATTERY_PATH

def load_battery(path: Path | None = None) -> dict[str, Any]:
    p=battery_config_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"charge_start": 40, "charge_stop": 80, "health_check": True}
    return {"charge_start": max(20, min(50, int(data.get("charge_start",40)))), "charge_stop": max(60, min(100, int(data.get("charge_stop",80)))), "health_check": bool(data.get("health_check", True))}

def save_battery(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=battery_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth battery — charge thresholds, offline\n"]
    lines.append(f'charge_start = {int(cfg.get("charge_start",40))}')
    lines.append(f'charge_stop = {int(cfg.get("charge_stop",80))}')
    lines.append(f'health_check = {str(bool(cfg.get("health_check",True))).lower()}')
    tmp = p.with_suffix(".tmp")
    tmp.write_text("\n".join(lines)+"\n", encoding="utf-8")
    tmp.replace(p)
    return p

def read_battery_health() -> dict[str, Any]:
    # read sysfs cycle_count + capacity
    health={}
    for bat in Path("/sys/class/power_supply").glob("BAT*"):
        try:
            cap=Path(bat/"capacity").read_text().strip() if (bat/"capacity").exists() else "?"
            cycles=Path(bat/"cycle_count").read_text().strip() if (bat/"cycle_count").exists() else "?"
            health[bat.name]={"capacity":cap, "cycles":cycles}
        except (OSError, ValueError, RuntimeError) as exc:
            logger.debug("read_battery_health %s failed: %s", bat.name, exc, exc_info=True)
            pass
    return health

def ledger_path(path: Path | None = None) -> Path:
    return Path(path) if path else LEDGER_PATH

def append_ledger(entry: dict[str, Any], path: Path | None = None) -> Path:
    p=ledger_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    entry["ts"]=datetime.utcnow().isoformat()
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry)+"\n")
    return p
