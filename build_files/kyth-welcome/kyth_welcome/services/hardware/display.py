"""Display probes (kscreen / DRM)."""
from __future__ import annotations

import glob
import os
import re

from .types import HardwareProbe
from ..process import _command_stdout


def _strip_ansi(text: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
 # _strip_ansi

def _format_display_mode(mode: str) -> str:
    m = re.match(r'(\d+)x(\d+)@([\d.]+)', mode)
    if not m:
        return mode
    try:
        hz = float(m.group(3))
    except ValueError:
        return mode
    return f"{m.group(1)}×{m.group(2)} @ {hz:.0f}Hz"  # noqa: RUF001 — multiplication sign, deliberate typography
 # _format_display_mode

def _display_probe() -> HardwareProbe:
    kscreen_raw = _command_stdout(["kscreen-doctor", "-o"], timeout=8)

    if kscreen_raw:
        return _parse_kscreen_output(kscreen_raw)

    # Fallback: sysfs DRM enumeration (resolution only, no refresh rate)
    connected: list[str] = []
    for status_path in sorted(glob.glob("/sys/class/drm/card*/card*-*/status")):
        try:
            with open(status_path, encoding="utf-8") as fh:
                is_connected = fh.read().strip() == "connected"
            if not is_connected:
                continue
        except OSError:
            continue
        connector = os.path.basename(os.path.dirname(status_path))
        _, _, name = connector.partition("-")
        modes_path = os.path.join(os.path.dirname(status_path), "modes")
        try:
            with open(modes_path, encoding="utf-8") as fh:
                first_mode = fh.readline().strip()
        except OSError:
            first_mode = ""
        connected.append(f"{name}{': ' + first_mode if first_mode else ''}")

    if not connected:
        return HardwareProbe("Display", "dim", "No connected displays detected via DRM.", "kscreen-doctor unavailable and no DRM outputs found.")

    return HardwareProbe(
        "Display", "ok",
        f"{len(connected)} display{'s' if len(connected) > 1 else ''} connected.",
        "Outputs:\n" + "\n".join(f"  {c}" for c in connected) + "\n\n(Install kscreen for refresh rate and VRR details.)",
    )
 # _display_probe

def _parse_kscreen_output(raw: str) -> HardwareProbe:
    text = _strip_ansi(raw)

    outputs: list[dict] = []
    cur: dict | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("Output:"):
            if cur is not None:
                outputs.append(cur)
            parts = line.split()
            name = parts[2] if len(parts) > 2 else "Unknown"
            cur = {"name": name, "enabled": False, "connected": False,
                   "current_mode": None, "vrr": "", "hdr": "", "modes": []}
        elif cur is None:
            continue
        elif line == "enabled":
            cur["enabled"] = True
        elif line == "connected":
            cur["connected"] = True
        elif line.startswith("Modes:"):
            for token in line[6:].split():
                m = re.match(r'\d+:([\dx@.\d]+)([*!]*)', token)
                if not m:
                    continue
                mode_str = m.group(1)
                cur["modes"].append(mode_str)
                if "*" in m.group(2):
                    cur["current_mode"] = mode_str
        elif line.lower().startswith("vrr:"):
            cur["vrr"] = line.split(":", 1)[1].strip().lower()
        elif line.lower().startswith("hdr:"):
            cur["hdr"] = line.split(":", 1)[1].strip().lower()

    if cur is not None:
        outputs.append(cur)

    active = [o for o in outputs if o["connected"] and o["enabled"]]
    if not active:
        return HardwareProbe("Display", "dim", "No active displays detected.", text.strip()[:600])

    display_strs: list[str] = []
    details_parts: list[str] = []
    vrr_warnings: list[str] = []

    for out in active:
        mode = out["current_mode"] or (out["modes"][0] if out["modes"] else "")
        mode_fmt = _format_display_mode(mode) if mode else "unknown resolution"

        attrs: list[str] = []
        vrr = out["vrr"]
        hdr = out["hdr"]
        if vrr and vrr not in ("never", "incapable", ""):
            attrs.append(f"VRR {vrr}")
        if hdr == "enabled":
            attrs.append("HDR")

        label = out["name"] + ": " + mode_fmt
        if attrs:
            label += f" ({', '.join(attrs)})"
        display_strs.append(label)

        mode_list = ", ".join(out["modes"][:8])
        if len(out["modes"]) > 8:
            mode_list += f" (+{len(out['modes']) - 8} more)"
        detail_lines = [
            f"{out['name']}: {mode_fmt}",
            f"  VRR: {vrr or 'unknown'}",
            f"  HDR: {hdr or 'unknown'}",
        ]
        if mode_list:
            detail_lines.append(f"  Available: {mode_list}")
        details_parts.append("\n".join(detail_lines))

        # Warn if high-refresh monitor has VRR capable but disabled
        if vrr == "never":
            max_hz = 0.0
            for m_str in out["modes"]:
                hz_m = re.search(r'@([\d.]+)', m_str)
                if hz_m:
                    try:
                        max_hz = max(max_hz, float(hz_m.group(1)))
                    except ValueError:
                        continue
            if max_hz >= 100:
                vrr_warnings.append(
                    f"{out['name']} supports up to {max_hz:.0f}Hz but VRR/FreeSync is set to Never."
                )

    n = len(active)
    summary = f"{n} display{'s' if n > 1 else ''}: " + " · ".join(display_strs) + "."
    details = "\n\n".join(details_parts)

    if vrr_warnings:
        return HardwareProbe(
            "Display", "warn",
            summary,
            details + "\n\n" + "\n".join(vrr_warnings),
            "Enable VRR in System Settings → Display & Monitor for smoother gameplay.",
        )

    return HardwareProbe("Display", "ok", summary, details)
 # _parse_kscreen_output
