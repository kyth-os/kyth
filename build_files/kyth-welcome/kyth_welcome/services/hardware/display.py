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
    return f"{m.group(1)}×{m.group(2)} @ {hz:.0f}Hz"
 # _format_display_mode

def _cpu_probe() -> HardwareProbe:
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as fh:
            cpuinfo = fh.read()
    except OSError:
        return HardwareProbe("CPU", "dim", "Could not read CPU information.", "/proc/cpuinfo not accessible.")

    model = next(
        (line.split(":", 1)[1].strip() for line in cpuinfo.splitlines() if line.startswith("model name")),
        "Unknown CPU",
    )
    # Trim redundant suffix noise
    model = re.sub(r'\s+(CPU|Processor)\s*$', '', model, flags=re.IGNORECASE).strip()

    logical = sum(1 for line in cpuinfo.splitlines() if line.startswith("processor"))

    # Physical cores: Core(s) per socket × Socket(s) from lscpu
    physical: int | None = None
    lscpu_out = _command_stdout(["lscpu"], timeout=5)
    cores_per_sock = sockets = None
    for line in lscpu_out.splitlines():
        if line.startswith("Core(s) per socket:"):
            try:
                cores_per_sock = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        if line.startswith("Socket(s):"):
            try:
                sockets = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    if cores_per_sock and sockets:
        physical = cores_per_sock * sockets

    gov_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
    try:
        governor = open(gov_path).read().strip()
    except OSError:
        governor = None

    # sched-ext state
    scx_state: str | None = None
    try:
        scx_state = open("/sys/kernel/sched_ext/state").read().strip()
    except OSError:
        pass

    scx_scheduler: str | None = None
    try:
        with open("/etc/scx/scx_loader.conf") as fh:
            for line in fh:
                if line.startswith("SCX_SCHEDULER="):
                    scx_scheduler = line.split("=", 1)[1].strip()
                    break
    except OSError:
        pass

    details: list[str] = [f"Model:    {model}"]
    if physical and logical:
        smt = f" / {logical} threads (SMT on)" if logical > physical else ""
        details.append(f"Cores:    {physical}{smt}")
    elif logical:
        details.append(f"Logical CPUs: {logical}")
    if governor:
        details.append(f"Governor: {governor}")

    scx_blurb = ""
    if scx_state == "enabled" and scx_scheduler:
        short = scx_scheduler.replace("scx_", "")
        details.append(f"Scheduler: {scx_scheduler} via sched-ext (active)")
        scx_blurb = f" {short.upper()} gaming scheduler active."
    elif scx_state == "enabled":
        details.append("Scheduler: sched-ext active")
        scx_blurb = " sched-ext gaming scheduler active."
    elif scx_scheduler:
        svc = _run_command(["systemctl", "is-active", "scx_loader.service"], timeout=5)
        if svc and svc.returncode == 0:
            short = scx_scheduler.replace("scx_", "")
            details.append(f"Scheduler: {scx_scheduler} (scx_loader active)")
            scx_blurb = f" {short.upper()} gaming scheduler active."
        else:
            details.append(f"Scheduler: {scx_scheduler} configured — scx_loader not running")
    else:
        details.append("Scheduler: CFS (sched-ext not configured)")

    summary = model + "." + scx_blurb if not scx_blurb else model + "." + scx_blurb
    return HardwareProbe("CPU", "ok", summary, "\n".join(details))
 # _cpu_probe

def _memory_probe() -> HardwareProbe:
    try:
        meminfo: dict[str, str] = {}
        with open("/proc/meminfo") as fh:
            for line in fh:
                k, _, v = line.partition(":")
                meminfo[k.strip()] = v.strip()
    except OSError:
        return HardwareProbe("Memory", "dim", "Could not read memory information.", "/proc/meminfo not accessible.")

    def _kb(key: str) -> float:
        raw = meminfo.get(key, "0")
        try:
            return int(raw.split()[0])
        except (ValueError, IndexError):
            return 0.0

    total_kb = _kb("MemTotal")
    avail_kb = _kb("MemAvailable")
    total_gb = total_kb / (1024 * 1024)
    avail_gb = avail_kb / (1024 * 1024)
    used_gb  = total_gb - avail_gb

    if total_gb >= 32:
        tier, status = "excellent for gaming", "ok"
    elif total_gb >= 16:
        tier, status = "good for gaming", "ok"
    elif total_gb >= 8:
        tier, status = "adequate for most games", "ok"
    else:
        tier, status = "below recommended for modern games (16 GB+)", "warn"

    details = (
        f"Total:     {total_gb:.1f} GB\n"
        f"In use:    {used_gb:.1f} GB\n"
        f"Available: {avail_gb:.1f} GB"
    )

    swap_out = _command_stdout(["swapon", "--show=NAME,SIZE,TYPE", "--noheadings"], timeout=5)
    if swap_out:
        details += "\n\nSwap:\n" + "\n".join(f"  {l}" for l in swap_out.splitlines())

    return HardwareProbe("Memory", status, f"{total_gb:.0f} GB RAM — {tier}.", details)
 # _memory_probe

def _display_probe() -> HardwareProbe:
    kscreen_raw = _command_stdout(["kscreen-doctor", "-o"], timeout=8)

    if kscreen_raw:
        return _parse_kscreen_output(kscreen_raw)

    # Fallback: sysfs DRM enumeration (resolution only, no refresh rate)
    connected: list[str] = []
    for status_path in sorted(glob.glob("/sys/class/drm/card*/card*-*/status")):
        try:
            if open(status_path).read().strip() != "connected":
                continue
        except OSError:
            continue
        connector = os.path.basename(os.path.dirname(status_path))
        _, _, name = connector.partition("-")
        modes_path = os.path.join(os.path.dirname(status_path), "modes")
        try:
            first_mode = open(modes_path).readline().strip()
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

