"""PipeWire gaming — pipewire-gaming.toml, wireplumber drop-in only in gaming.

Quantum 128/48000 for low latency, otherwise 1024/48000 studio.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_PIPEWIRE_GAMING_PATH = Path("/etc/kyth/pipewire-gaming.toml")
DEFAULT_CONF = Path("/etc/wireplumber/main.lua.d/99-kyth-gaming.lua")
DEFAULT_QUANTUM_DROPIN = Path("/etc/pipewire/pipewire.conf.d/99-kyth-gaming.conf")
GAMING_QUANTUM = 128
BASE_QUANTUM_TEMPLATE = Path("/usr/share/kyth/pipewire-gaming-128.conf")


def pipewire_gaming_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "pipewire-gaming.toml"
    return DEFAULT_PIPEWIRE_GAMING_PATH


def load_pipewire_gaming(path: Path | None = None) -> dict[str, Any]:
    p = pipewire_gaming_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced", "quantum": 128}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    try:
        q = int(data.get("quantum", 128))
    except (TypeError, ValueError):
        q = 128
    q = max(32, min(2048, q))
    return {"profile": prof, "quantum": q}


def save_pipewire_gaming(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = pipewire_gaming_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    q = int(cfg.get("quantum", 128))
    lines = [
        "# Kyth PipeWire gaming — offline",
        f'profile = "{prof}"',
        f"quantum = {q}",
        "",
    ]
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def _write_quantum_dropin(quantum: int, dest: Path) -> Path:
    """Install the low-latency quantum drop-in (sorts after the 1024 base)."""
    lines = [
        "# Kyth PipeWire gaming — applied only while the gaming profile is active",
        "context.properties = {",
        "    default.clock.rate          = 48000",
        f"    default.clock.quantum       = {quantum}",
        "    default.clock.min-quantum   = 64",
        "    default.clock.max-quantum   = 8192",
        "    default.clock.allowed-rates = [ 44100 48000 ]",
        "}",
        "",
    ]
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(dest)
    return dest


def _remove_quantum_dropin(dest: Path) -> None:
    try:
        if dest.exists():
            dest.unlink()
    except OSError:
        pass


def generate_pipewire_gaming(
    cfg: dict[str, Any] | None = None,
    dest: Path | None = None,
    quantum_dest: Path | None = None,
) -> Path | None:
    if cfg is None:
        cfg = load_pipewire_gaming()
    dest = dest or DEFAULT_CONF
    quantum_dropin = quantum_dest or DEFAULT_QUANTUM_DROPIN
    if str(cfg.get("profile", "balanced")) != "gaming":
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        _remove_quantum_dropin(quantum_dropin)
        return None
    q = int(cfg.get("quantum", GAMING_QUANTUM))
    lines = [
        "-- Kyth PipeWire gaming — generated",
        "table.insert(alsa_monitor.rules, {",
        '  matches = {{{ "node.name", "matches", "alsa_output.*" }}},',
        "  apply_properties = {",
        f'    ["api.alsa.period-size"] = {q},',
        f'    ["api.alsa.headroom"] = {q},',
        "  },",
        "})",
        "",
    ]
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(dest)
    _write_quantum_dropin(q, quantum_dropin)
    return dest


def pipewire_gaming_status(conf: Path = DEFAULT_CONF) -> str:
    return "gaming" if conf.exists() else "balanced"
