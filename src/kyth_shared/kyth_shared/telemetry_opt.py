"""Telemetry privacy — telemetry-opt.toml, opt-out dash."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_TELEMETRY_OPT_PATH = Path("/etc/kyth/telemetry-opt.toml")


def telemetry_opt_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "telemetry-opt.toml"
    return DEFAULT_TELEMETRY_OPT_PATH


def load_telemetry_opt(path: Path | None = None) -> dict[str, Any]:
    p = telemetry_opt_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"enabled": True, "collectors": []}
    en = bool(data.get("enabled", True))
    cols = data.get("collectors", [])
    if not isinstance(cols, list):
        cols = []
    cols = [str(c) for c in cols if isinstance(c, str)]
    return {"enabled": en, "collectors": cols}


def save_telemetry_opt(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = telemetry_opt_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    en = bool(cfg.get("enabled", True))
    cols = [str(c) for c in cfg.get("collectors", []) if isinstance(c, str)] if isinstance(cfg.get("collectors"), list) else []
    cols_s = ", ".join(f'"{c}"' for c in cols)
    p.write_text(f"# Kyth telemetry opt — offline\nenabled = {str(en).lower()}\ncollectors = [{cols_s}]\n", encoding="utf-8")
    return p


def telemetry_collectors_status(path: Path | None = None) -> list[str]:
    """Return effective collectors — empty when purged/disabled."""
    cfg = load_telemetry_opt(path)
    if not cfg.get("enabled") or not cfg.get("collectors"):
        return []
    try:
        from .system.probe import default_collectors

        allowed = {c.name for c in default_collectors()}
        return [c for c in cfg["collectors"] if c in allowed]
    except Exception:
        return []


def purge_telemetry_opt(path: Path | None = None) -> Path:
    """Purge collectors and assert empty — auditable off switch."""
    p = save_telemetry_opt({"enabled": False, "collectors": []}, path)
    assert telemetry_collectors_status(path) == [], "purge failed: collectors still reported"
    return p
