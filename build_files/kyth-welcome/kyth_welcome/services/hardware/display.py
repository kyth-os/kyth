"""Display probes (kscreen / DRM)."""
from __future__ import annotations

import glob
import os
import re

from .types import HardwareProbe
from ..process import command_stdout, strip_ansi


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
    kscreen_raw = command_stdout(["kscreen-doctor", "-o"], timeout=8)

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
        return HardwareProbe("Display", "dim", "No connected displays detected — switcher check: your monitor may need a cable re-seat.", "kscreen-doctor unavailable and no DRM outputs found. Check System Hub → Hardware after logging in.")

    return HardwareProbe(
        "Display", "ok",
        f"{len(connected)} display{'s' if len(connected) > 1 else ''} connected.",
        "Outputs:\n" + "\n".join(f"  {c}" for c in connected) +
        "\n\n(For refresh rate + VRR/HDR details, open System Hub → Hardware → Display; kscreen provides full mode list.)",
    )


# _display_probe


def _parse_kscreen_output(raw: str) -> HardwareProbe:
    text = strip_ansi(raw)
    outputs = _extract_outputs_from_kscreen(text)

    active = [o for o in outputs if o["connected"] and o["enabled"]]
    if not active:
        return HardwareProbe("Display", "dim", "No active displays detected.", text.strip()[:600])

    display_strs, details_parts, vrr_warnings = _build_display_info(active)
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


def _extract_outputs_from_kscreen(text: str) -> list[dict]:
    """Parse kscreen-doctor output into a list of output dictionaries."""
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

    return outputs


def _build_display_info(active: list[dict]) -> tuple[list[str], list[str], list[str]]:
    """Build display strings, details, and VRR warnings from active outputs."""
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

    return display_strs, details_parts, vrr_warnings


# _parse_kscreen_output


def hdr_vrr_status_text(raw: str) -> str:
    """Compact per-output HDR/VRR summary for page_hardware.py's Display
    card, parsed from `kscreen-doctor -o` output. Distinct from the fuller
    _parse_kscreen_output() probe above — this only reports HDR/VRR state,
    not resolution/enabled/connected."""
    hdr_outputs: list[tuple[str, str]] = []   # (name, hdr_state)
    vrr_outputs: list[tuple[str, str]] = []   # (name, vrr_state)
    if raw:
        cur_name = ""
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("Output:") or (stripped and not line.startswith(" ")):
                parts = stripped.split()
                if len(parts) >= 2:
                    cur_name = parts[-1].rstrip(":")
            elif stripped.lower().startswith("hdr:") and cur_name:
                hdr_outputs.append((cur_name, stripped.split(":", 1)[1].strip()))
            elif stripped.lower().startswith("vrr:") and cur_name:
                vrr_outputs.append((cur_name, stripped.split(":", 1)[1].strip()))

    if hdr_outputs or vrr_outputs:
        lines = []
        seen = set()
        for name, hdr in hdr_outputs:
            seen.add(name)
            vrr = next((v for n, v in vrr_outputs if n == name), "unknown")
            hdr_str = "HDR on" if hdr == "enabled" else "HDR off"
            vrr_str = f"VRR {vrr}" if vrr not in ("unknown", "") else "VRR unknown"
            lines.append(f"{name}: {hdr_str}  ·  {vrr_str}")
        for name, vrr in vrr_outputs:
            if name not in seen:
                lines.append(f"{name}: VRR {vrr}")
        return "\n".join(lines)
    return "Display info unavailable — kscreen not running or no outputs detected."
