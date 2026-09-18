"""Per-display HDR mastering — EDID → store + kscreen-doctor apply.

Parses EDID for peak luminance hints, persists ``~/.config/kyth/display-hdr.toml``,
and applies HDR/WCG + SDR brightness via ``kscreen-doctor`` when a Wayland
session is live.
"""
from __future__ import annotations

import logging
import math
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
_CONNECTOR_RE = re.compile(r"^([A-Za-z]+)(?:-A)?-?(\d+)$")

#: EDID fallback when no HDR static metadata block parses: a safe SDR-room
#: assumption, never 0 (which would crush SDR brightness mapping).
EDID_FALLBACK_PEAK_NITS = 400


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
            peak = int(entry.get("peak_nits", EDID_FALLBACK_PEAK_NITS))
        except (TypeError, ValueError):
            peak = EDID_FALLBACK_PEAK_NITS
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
        peak = int(entry.get("peak_nits", EDID_FALLBACK_PEAK_NITS))
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
    return cfg.get(connector, {"peak_nits": EDID_FALLBACK_PEAK_NITS, "hdr_enabled": False, "sdr_nits": 200})


def set_display_hdr(
    connector: str,
    peak_nits: int = EDID_FALLBACK_PEAK_NITS,
    hdr_enabled: bool = False,
    sdr_nits: int = 200,
    path: Path | None = None,
) -> Path:
    cfg = load_hdr_config(path)
    cfg[str(connector)] = {"peak_nits": peak_nits, "hdr_enabled": hdr_enabled, "sdr_nits": sdr_nits}
    return save_hdr_config(cfg, path)


def normalize_connector(name: str) -> tuple[str, int] | None:
    """Split ``HDMI-A-1``/``HDMI-1``/``DP-2`` into (FAMILY, index) for rename matching."""
    match = _CONNECTOR_RE.match(name.strip())
    if not match:
        return None
    return (match.group(1).upper(), int(match.group(2)))


def match_connector(name: str, displays: dict[str, Any]) -> str | None:
    """Find the config key for a connected output, tolerating renames.

    Exact match first, then same family+index (``HDMI-A-1`` vs ``HDMI-1``),
    then any same-family entry (lowest index — the common replug reorder).
    """
    if name in displays:
        return name
    wanted = normalize_connector(name)
    if wanted is None:
        return None
    family_matches: list[tuple[int, str]] = []
    for key in displays:
        if key == name:
            return key
        candidate = normalize_connector(key)
        if candidate is None:
            continue
        if candidate == wanted:
            return key
        if candidate[0] == wanted[0]:
            family_matches.append((candidate[1], key))
    if family_matches:
        return sorted(family_matches)[0][1]
    return None


def parse_edid_peak_nits(edid_path: Path) -> int | None:
    """Peak nits from the CTA-861 HDR static metadata block, else None.

    Walks every CEA-861 extension's data-block collection for extended tag
    0x06 and converts desired-content-max-luminance (CV) per CTA-861.3
    (50 * 2^(CV/32) cd/m²), clamped to the load/save range. Callers fall back
    to :data:`EDID_FALLBACK_PEAK_NITS` on None.
    """
    try:
        data = edid_path.read_bytes()
    except OSError:
        return None
    if len(data) < 128:
        return None
    ext_count = data[126]
    for ext in range(ext_count):
        base = 128 * (ext + 1)
        if len(data) < base + 128:
            break
        block = data[base : base + 128]
        if block[0] != 0x02:  # not a CEA-861 extension
            continue
        dtd_offset = block[2]
        if dtd_offset < 4 or dtd_offset > 128:
            continue
        pos = 4
        while pos < dtd_offset:
            header = block[pos]
            tag = (header >> 5) & 0x07
            length = header & 0x1F
            pos += 1
            if pos + length > dtd_offset:
                break
            payload = block[pos : pos + length]
            pos += length
            if tag == 0x07 and length >= 4 and payload[0] == 0x06:
                cv = payload[3]
                if cv == 0:
                    continue  # unknown — keep looking
                try:
                    nits = int(round(50.0 * math.pow(2.0, cv / 32.0)))
                except (OverflowError, ValueError):
                    continue
                return max(100, min(4000, nits))
    return None


def edid_peak_nits_or_default(edid_path: Path, default: int = EDID_FALLBACK_PEAK_NITS) -> int:
    """Parse EDID peak nits, returning *default* (400) when unparseable."""
    parsed = parse_edid_peak_nits(edid_path)
    return parsed if parsed is not None else default


def discover_peak_nits(sysfs_root: Path = Path("/sys/class/drm")) -> dict[str, int]:
    """Map connected DRM connectors to EDID peak nits (400 fallback each)."""
    found: dict[str, int] = {}
    try:
        cards = list(sysfs_root.iterdir())
    except OSError:
        return found
    for card in cards:
        edid = card / "edid"
        status = card / "status"
        try:
            if not edid.is_file():
                continue
            if status.is_file() and status.read_text(encoding="utf-8").strip() != "connected":
                continue
            found[card.name] = edid_peak_nits_or_default(edid)
        except OSError:
            continue
    return found


def kwin_hdr_env_for_connector(connector: str, path: Path | None = None) -> dict[str, str]:
    """Env hints for launch wrappers (games scope / gamescope) — not read by KWin."""
    entry = get_display_hdr(connector, path)
    if not entry.get("hdr_enabled"):
        return {}
    peak = int(entry.get("peak_nits", EDID_FALLBACK_PEAK_NITS))
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
    Config keys are matched rename-tolerantly (see :func:`match_connector`) so
    a replug reorder (DP-1 → DP-2) does not orphan the stored calibration.
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
            key = match_connector(name, displays)
            if key is not None:
                targets[name] = dict(displays[key])
    elif force_enable is not None:
        for name in connected:
            targets[name] = {"hdr_enabled": force_enable, "sdr_nits": 200, "peak_nits": EDID_FALLBACK_PEAK_NITS}

    if force_enable is not None:
        for name in list(targets):
            targets[name]["hdr_enabled"] = force_enable
        if not targets:
            for name in connected:
                targets[name] = {"hdr_enabled": force_enable, "sdr_nits": 200, "peak_nits": EDID_FALLBACK_PEAK_NITS}

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
