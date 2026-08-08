"""Peripherals Just Works Hub — unified scan (welcome-side, Qt-free logic uses run adapter)."""
from __future__ import annotations

import shutil
from pathlib import Path


def _run_text(cmd: list[str], timeout: int = 4) -> tuple[int, str]:
    try:
        from kyth_shared.commands import run as _run
        r = _run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception:
        return 127, ""


def scan_peripherals() -> dict:
    result: dict = {
        "rgb": {"available": False, "tool": None, "detail": ""},
        "fan": {"available": False, "detail": ""},
        "controllers": {"available": False, "count": 0, "detail": ""},
        "hdr": {"available": False, "detail": ""},
        "audio": {"available": False, "detail": ""},
    }

    # RGB
    for tool in ("openrgb", "kyth-apply-rgb"):
        if shutil.which(tool):
            result["rgb"] = {"available": True, "tool": tool, "detail": f"{tool} installed — System Hub → Hardware → RGB"}
            break
    if not result["rgb"]["available"]:
        result["rgb"]["detail"] = "No RGB tool found — install OpenRGB via App Store or run kyth-apply-rgb."

    # Fan
    try:
        fan_toml = Path("/etc/kyth/fan-curve.toml")
        hwmon = any(Path(f"/sys/class/hwmon/hwmon{i}").exists() for i in range(6))
        if fan_toml.exists() or hwmon:
            result["fan"] = {"available": True, "detail": "Fan curve available — System Hub → Hardware → Cooling" if hwmon else "fan-curve.toml present"}
        else:
            result["fan"]["detail"] = "No hwmon fan control detected on this hardware."
    except Exception:
        pass

    # Controllers
    try:
        js = [p for p in Path("/dev/input").glob("js*") if p.exists()]
        ev = [p for p in Path("/dev/input/by-id").glob("*") if "controller" in p.name.lower() or "xbox" in p.name.lower() or "sony" in p.name.lower()]
        count = len(js) + len(ev)
        if count > 0:
            result["controllers"] = {"available": True, "count": count, "detail": f"{count} controller device(s) detected — test via ujust controller-check"}
        else:
            result["controllers"]["detail"] = "No controllers detected — connect via USB/Bluetooth and run controller-check."
    except Exception:
        pass

    # HDR
    code, txt = _run_text(["kscreen-doctor", "-o"], timeout=4)
    if code == 0 and "hdr" in txt.lower():
        result["hdr"] = {"available": True, "detail": "HDR capability advertised — enable per-game via Gaming → HDR"}
    elif code == 0:
        result["hdr"] = {"available": True, "detail": "HDR not advertised on current display; enable per-game via Gaming → HDR when available."}
    else:
        result["hdr"] = {"available": True, "detail": "Install kscreen-doctor to probe HDR; per-game HDR lives in Gaming → HDR."}

    # Audio
    for cmd in (["wpctl", "status"], ["pactl", "list", "short", "sinks"]):
        code, txt = _run_text(cmd, timeout=3)
        if code == 0 and txt.strip():
            sinks = [l for l in txt.splitlines() if l.strip()]
            result["audio"] = {"available": True, "count": len(sinks), "detail": f"PipeWire audio ready — {len(sinks)} sink(s); per-app mixer in Repair → Quick Fixes"}
            break
    if not result["audio"]["available"]:
        result["audio"]["detail"] = "PipeWire not ready — restart via Repair → Quick Fixes → Restart Audio."

    return result
