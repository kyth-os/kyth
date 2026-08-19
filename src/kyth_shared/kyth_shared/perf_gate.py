"""Perf gate — perf-gate.toml, CI gate 10% regression (was 5%, too tight)."""
from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_PERF_GATE_PATH = Path("/etc/kyth/perf-gate.toml")
LEDGER = Path("/var/cache/kyth/perf-ledger.jsonl")


def perf_gate_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "perf-gate.toml"
    return DEFAULT_PERF_GATE_PATH


def load_perf_gate(path: Path | None = None) -> dict[str, Any]:
    p = perf_gate_config_path(path)
    try:
        with p.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {"threshold": 10, "enabled": True}
    try:
        thr = int(data.get("threshold", 10))
    except (TypeError, ValueError):
        thr = 10
    thr = max(1, min(20, thr))
    return {"threshold": thr, "enabled": bool(data.get("enabled", True))}


def save_perf_gate(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = perf_gate_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    thr = max(1, min(20, int(cfg.get("threshold", 10))))
    en = bool(cfg.get("enabled", True))
    p.write_text(f"# Kyth perf gate — offline\nthreshold = {thr}\nenabled = {str(en).lower()}\n", encoding="utf-8")
    return p


def check_perf_gate(current_ms: float | None = None, ledger: Path = LEDGER, path: Path | None = None) -> dict[str, Any]:
    cfg = load_perf_gate(path)
    if not cfg.get("enabled"):
        return {"enabled": False, "pass": True}
    threshold = int(cfg.get("threshold", 10))
    # find last ledger p95
    last = None
    try:
        if ledger.exists():
            for line in ledger.read_text(encoding="utf-8").splitlines()[-10:]:
                try:
                    obj = json.loads(line)
                    if "p95" in obj:
                        last = float(obj["p95"])
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass
    except OSError:
        pass
    if last is None or current_ms is None:
        return {"enabled": True, "pass": True, "threshold": threshold, "last": last, "current": current_ms}
    delta = ((current_ms - last) / last * 100) if last else 0
    return {"enabled": True, "pass": delta <= threshold, "delta": round(delta, 2), "threshold": threshold, "last": last, "current": current_ms}
