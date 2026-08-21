"""Per-display HDR mastering — EDID → store + kscreen-doctor apply.

Parses EDID for peak luminance hints, persists ``~/.config/kyth/display-hdr.toml``,
and applies HDR/WCG + SDR brightness via ``kscreen-doctor`` when a Wayland
session is live.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tomllib
from pathlib import Path
from typing import Any

from kyth_shared.atomic_io import atomic_write_text as _atomic_write_text
from kyth_shared.commands import run
from kyth_shared.guardian_actions import parse_kscreen_outputs

logger = logging.getLogger(__name__)

DEFAULT_HDR_PATH = Path.home() / ".config" / "kyth" / "display-hdr.toml"
_OUTPUT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def hdr_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "kyth" / "display-hdr.toml"
    return DEFAULT_HDR_PATH


def load_hdr_config(path: Path | None = None) -> dict[str, dict[str, Any]]:
    cfg_path = hdr_config_path(path)
    try:
        with cfg_path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    displays = data.get("displays", {})
    if not isinstance(displays, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for conn, entry in displays.items():
        if not isinstance(entry, dict):
            continue
        try:
            peak = int(entry.get("peak_nits", 400))
        except (TypeError, ValueError):
            peak = 400
        peak = max(100, min(4000, peak))
        hdr = bool(entry.get("hdr_enabled", False))
        try:
            sdr_nits = int(entry.get("sdr_nits", 200))
        except (TypeError, ValueError):
            sdr_nits = 200
        sdr_nits = max(80, min(600, sdr_nits))
        out[str(conn)] = {"peak_nits": peak, "hdr_enabled": hdr, "sdr_nits": sdr_nits}
    return out


def save_hdr_config(displays: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    cfg_path = hdr_config_path(path)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Kyth per-display HDR mastering — EDID + KWin\n"]
    for conn in sorted(displays):
        entry = displays[conn]
        peak = int(entry.get("peak_nits", 400))
        hdr = bool(entry.get("hdr_enabled", False))
        sdr_nits = int(entry.get("sdr_nits", 200))
        lines.append(f'[displays."{conn}"]')
        lines.append(f"peak_nits = {peak}")
        lines.append(f"hdr_enabled = {str(hdr).lower()}")
        lines.append(f"sdr_nits = {sdr_nits}")
        lines.append("")
    _atomic_write_text(cfg_path, "\n".join(lines), encoding="utf-8")
    return cfg_path


def get_display_hdr(connector: str, path: Path | None = None) -> dict[str, Any]:
    cfg = load_hdr_config(path)
    return cfg.get(connector, {"peak_nits": 400, "hdr_enabled": False, "sdr_nits": 200})


def set_display_hdr(
    connector: str,
    peak_nits: int = 400,
    hdr_enabled: bool = False,
    sdr_nits: int = 200,
    path: Path | None = None,
) -> Path:
    cfg = load_hdr_config(path)
    cfg[str(connector)] = {"peak_nits": peak_nits, "hdr_enabled": hdr_enabled, "sdr_nits": sdr_nits}
    return save_hdr_config(cfg, path)


def parse_edid_peak_nits(edid_path: Path) -> int | None:
    try:
        data = edid_path.read_bytes()
        if len(data) < 128:
            return None
        ext = data[126]
        if ext > 0 and len(data) >= 256:
            for i in range(128, min(len(data), 512)):
                if data[i] == 0x06 and i + 3 < len(data):
                    maybe = data[i + 2]
                    if 1 <= maybe <= 10:
                        return maybe * 100
        return None
    except OSError:
        return None


def kwin_hdr_env_for_connector(connector: str, path: Path | None = None) -> dict[str, str]:
    """Env hints for launch wrappers (games scope / gamescope) — not read by KWin."""
    entry = get_display_hdr(connector, path)
    if not entry.get("hdr_enabled"):
        return {}
    peak = int(entry.get("peak_nits", 400))
    sdr = int(entry.get("sdr_nits", 200))
    return {"KYTH_HDR": "1", "KYTH_HDR_PEAK_NITS": str(peak), "KYTH_HDR_SDR_NITS": str(sdr)}


def apply_display_hdr(
    displays: dict[str, dict[str, Any]] | None = None,
    *,
    force_enable: bool | None = None,
) -> list[str]:
    """Apply display-hdr.toml via kscreen-doctor (Wayland session).

    If *force_enable* is set, override per-display ``hdr_enabled`` for all
    connected outputs listed in the config (or all connected when config empty).
    """
    if displays is None:
        displays = load_hdr_config()
    if os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland":
        return ["hdr skipped: not a Wayland session"]
    if not shutil.which("kscreen-doctor"):
        return ["kscreen-doctor unavailable"]

    listed = run(["kscreen-doctor", "-o"], capture_output=True, timeout=8, check=False)
    if listed.returncode != 0:
        return ["kscreen-doctor -o failed"]
    connected = [
        str(o.get("name") or "")
        for o in parse_kscreen_outputs(listed.stdout or "")
        if o.get("connected") and _OUTPUT_NAME_RE.fullmatch(str(o.get("name") or ""))
    ]
    if not connected:
        return ["no connected outputs"]

    targets: dict[str, dict[str, Any]] = {}
    if displays:
        for name in connected:
            if name in displays:
                targets[name] = dict(displays[name])
    elif force_enable is not None:
        for name in connected:
            targets[name] = {"hdr_enabled": force_enable, "sdr_nits": 200, "peak_nits": 400}

    if force_enable is not None:
        for name in list(targets):
            targets[name]["hdr_enabled"] = force_enable
        if not targets:
            for name in connected:
                targets[name] = {"hdr_enabled": force_enable, "sdr_nits": 200, "peak_nits": 400}

    applied: list[str] = []
    for name, entry in targets.items():
        enable = bool(entry.get("hdr_enabled", False))
        action = "enable" if enable else "disable"
        cmd = [
            "kscreen-doctor",
            f"output.{name}.hdr.{action}",
            f"output.{name}.wcg.{action}",
        ]
        sdr = int(entry.get("sdr_nits", 200))
        if enable:
            cmd.append(f"output.{name}.sdr-brightness.{sdr}")
        res = run(cmd, capture_output=True, timeout=12, check=False)
        if res.returncode == 0:
            note = f"{name}.hdr.{action}"
            if enable:
                note += f",sdr={sdr}"
            applied.append(note)
        else:
            applied.append(f"{name}.hdr.{action} failed")
    return applied or ["nothing to apply"]
