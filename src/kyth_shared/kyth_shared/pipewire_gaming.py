"""PipeWire gaming — pipewire-gaming.toml, wireplumber drop-in only in gaming.

Quantum 128/48000 for low latency, otherwise 1024/48000 studio.

Bluetooth guard: a global 128-sample quantum starves BT codecs (SBC/LDAC
need headroom for retransmits) into stutter, so when a Bluetooth audio sink
is active the gaming profile still applies its ALSA wireplumber rules but
skips the global quantum drop-in and stays on the conservative base clock.
Wired/USB gaming audio is unaffected.
"""

from __future__ import annotations

import os
import shutil
import tomllib
from pathlib import Path
from typing import Any

from kyth_shared.commands import run_optional

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


def bluetooth_audio_active() -> bool:
    """True when a Bluetooth audio sink looks active (best-effort, offline).

    Checks PipeWire/Pulse sinks for a BlueZ device first, then falls back to
    ``bluetoothctl`` connected-device output. Any probe failure means "no
    evidence" (False) — the guard only trips on positive signal, so a
    missing bluetooth stack never blocks the gaming profile.
    """
    for argv in (
        ["pactl", "list", "sinks", "short"],
        ["pw-cli", "list-objects", "Node"],
    ):
        if not shutil.which(argv[0]):
            continue
        proc = run_optional(argv, capture_output=True, text=True, timeout=10)
        if proc is None:
            continue
        if "bluez" in proc.stdout.lower() or "bluetooth" in proc.stdout.lower():
            return True
    if shutil.which("bluetoothctl"):
        proc = run_optional(
            ["bluetoothctl", "devices", "Connected"],
            capture_output=True, text=True, timeout=10,
        )
        if proc is not None:
            lines = [
                line for line in proc.stdout.splitlines()
                if line.strip() and "no default controller" not in line.lower()
            ]
            if lines:
                return True
    return False


def generate_pipewire_gaming(
    cfg: dict[str, Any] | None = None,
    dest: Path | None = None,
    quantum_dest: Path | None = None,
    bt_active: bool | None = None,
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
    if bt_active is None:
        bt_active = bluetooth_audio_active()
    if bt_active:
        # Bluetooth headset guard: a BT sink is active, so skip the global
        # 128-sample quantum (SBC/LDAC stutter without headroom) and clear
        # any stale drop-in. The ALSA wireplumber rules below only match
        # alsa_output.* — wired/USB gaming audio keeps low latency.
        _remove_quantum_dropin(quantum_dropin)
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
    if not bt_active:
        _write_quantum_dropin(q, quantum_dropin)
    return dest


def pipewire_gaming_status(conf: Path = DEFAULT_CONF) -> str:
    return "gaming" if conf.exists() else "balanced"
