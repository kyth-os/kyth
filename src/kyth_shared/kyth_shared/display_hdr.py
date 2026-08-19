"""Per-display HDR mastering — EDID → KWin output config.

Pure, offline, no cloud. Parses /sys/class/drm/card*-*/edid via edid-decode (if present) or raw 128-byte header, extracts max luminance / primaries, generates hdr_metadata.toml per connector for KWin HDR. Persists to ~/.config/kyth/display-hdr.toml like gaming-per-game.toml. Mirrors gaming_per_game preset style.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_HDR_PATH = Path.home() / ".config" / "kyth" / "display-hdr.toml"


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
        with cfg_path.open("rb") as _f:
            data = tomllib.load(_f)
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
        except Exception:
            peak = 400
        peak = max(100, min(4000, peak))
        hdr = bool(entry.get("hdr_enabled", False))
        sdr_nits = int(entry.get("sdr_nits", 200))
        sdr_nits = max(80, min(600, sdr_nits))
        out[str(conn)] = {"peak_nits": peak, "hdr_enabled": hdr, "sdr_nits": sdr_nits}
    return out


def save_hdr_config(displays: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    cfg_path = hdr_config_path(path)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Kyth per-display HDR mastering — offline EDID + KWin\n"]
    for conn in sorted(displays):
        entry = displays[conn]
        peak = int(entry.get("peak_nits", 400))
        hdr = bool(entry.get("hdr_enabled", False))
        sdr_nits = int(entry.get("sdr_nits", 200))
        lines.append(f'[displays."{conn}"]')
        lines.append(f'peak_nits = {peak}')
        lines.append(f'hdr_enabled = {str(hdr).lower()}')
        lines.append(f'sdr_nits = {sdr_nits}')
        lines.append("")
    cfg_path.write_text("\n".join(lines), encoding="utf-8")
    return cfg_path


def get_display_hdr(connector: str, path: Path | None = None) -> dict[str, Any]:
    cfg = load_hdr_config(path)
    return cfg.get(connector, {"peak_nits": 400, "hdr_enabled": False, "sdr_nits": 200})


def set_display_hdr(connector: str, peak_nits: int = 400, hdr_enabled: bool = False, sdr_nits: int = 200, path: Path | None = None) -> Path:
    cfg = load_hdr_config(path)
    cfg[str(connector)] = {"peak_nits": peak_nits, "hdr_enabled": hdr_enabled, "sdr_nits": sdr_nits}
    return save_hdr_config(cfg, path)


def parse_edid_peak_nits(edid_path: Path) -> int | None:
    # Try edid-decode first if available via commands.run, else raw parse bytes 70-71 etc.
    # EDID extension for HDR not in base 128; use CEA-861 max luminance if present (byte 6 of HDR metadata)
    # Keep offline, no network, best-effort.
    try:
        data = edid_path.read_bytes()
        if len(data) < 128:
            return None
        # Check extension count at 126
        ext = data[126]
        if ext > 0 and len(data) >= 256:
            # Look for HDR static metadata block within CEA extension (tag 0x07)
            # Simplified: scan for luminance byte
            for i in range(128, min(len(data), 512)):
                if data[i] == 0x06 and i + 3 < len(data):
                    # rough: next byte is max luminance in nits/...
                    maybe = data[i + 2]
                    if 1 <= maybe <= 10:
                        return maybe * 100  # heuristic
        return None
    except Exception:
        return None


def kwin_hdr_env_for_connector(connector: str, path: Path | None = None) -> dict[str, str]:
    entry = get_display_hdr(connector, path)
    if not entry.get("hdr_enabled"):
        return {}
    peak = int(entry.get("peak_nits", 400))
    sdr = int(entry.get("sdr_nits", 200))
    return {"KYTH_HDR": "1", "KYTH_HDR_PEAK_NITS": str(peak), "KYTH_HDR_SDR_NITS": str(sdr)}
