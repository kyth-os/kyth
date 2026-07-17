"""System probes: CPU, memory, thermal, storage, platform."""
from __future__ import annotations

import glob
import os
import re
import shutil

from .types import HardwareProbe
from ..bootc import _branch_display_name, _current_branch, _has_staged_update
from ..process import _command_stdout, _run_command


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


def _thermal_probe() -> HardwareProbe:
    cpu_readings: dict[str, float] = {}
    gpu_readings: dict[str, float] = {}

    for hwmon_dir in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        try:
            name = open(os.path.join(hwmon_dir, "name")).read().strip()
        except OSError:
            continue

        is_cpu = name in ("k10temp", "coretemp", "zenpower", "nct6798", "it8686")
        is_gpu = name in ("amdgpu", "radeon", "nouveau")
        if not is_cpu and not is_gpu:
            continue

        for temp_input in sorted(glob.glob(os.path.join(hwmon_dir, "temp*_input"))):
            label_file = temp_input.replace("_input", "_label")
            label = ""
            try:
                if os.path.exists(label_file):
                    label = open(label_file).read().strip()
            except OSError:
                pass
            try:
                temp_c = int(open(temp_input).read().strip()) / 1000.0
            except (OSError, ValueError):
                continue
            if not (1 < temp_c < 130):
                continue

            key = label if label else os.path.basename(temp_input).replace("_input", "")
            if is_cpu:
                cpu_readings[key] = temp_c
            else:
                gpu_readings[key] = temp_c

    if not cpu_readings and not gpu_readings:
        return HardwareProbe(
            "Thermal", "dim",
            "No temperature sensors detected.",
            "hwmon drivers (k10temp, amdgpu) must be loaded for temperature monitoring.",
        )

    details_parts: list[str] = []
    hot: list[str] = []

    if cpu_readings:
        # Prefer Tdie for AMD (Tctl adds a 10°C offset), or Package for Intel
        cpu_display_temp = (
            cpu_readings.get("Tdie")
            or cpu_readings.get("Package id 0")
            or next(iter(cpu_readings.values()))
        )
        cpu_lines = "\n".join(f"  {k}: {v:.0f}°C" for k, v in sorted(cpu_readings.items()))
        details_parts.append(f"CPU:\n{cpu_lines}")
        if cpu_display_temp > 90:
            hot.append(f"CPU at {cpu_display_temp:.0f}°C — check cooling.")
        elif cpu_display_temp > 80:
            hot.append(f"CPU at {cpu_display_temp:.0f}°C — warm, monitor under load.")

    if gpu_readings:
        gpu_display_temp = (
            gpu_readings.get("junction")
            or gpu_readings.get("edge")
            or next(iter(gpu_readings.values()))
        )
        gpu_lines = "\n".join(f"  {k}: {v:.0f}°C" for k, v in sorted(gpu_readings.items()))
        details_parts.append(f"GPU:\n{gpu_lines}")
        if gpu_display_temp > 90:
            hot.append(f"GPU at {gpu_display_temp:.0f}°C — check airflow.")

    summary_parts: list[str] = []
    if cpu_readings:
        t = cpu_readings.get("Tdie") or cpu_readings.get("Package id 0") or next(iter(cpu_readings.values()))
        summary_parts.append(f"CPU {t:.0f}°C")
    if gpu_readings:
        t = gpu_readings.get("junction") or gpu_readings.get("edge") or next(iter(gpu_readings.values()))
        summary_parts.append(f"GPU {t:.0f}°C")

    summary = "Temperatures: " + ", ".join(summary_parts) + "."
    details = "\n\n".join(details_parts)
    status = "warn" if hot else "ok"
    action = "  ".join(hot) if hot else None

    return HardwareProbe("Thermal", status, summary + (" " + "  ".join(hot) if hot else ""), details, action)
 # _thermal_probe


def _storage_probe() -> HardwareProbe:
    usage = shutil.disk_usage("/home")
    free_pct = (usage.free / usage.total) * 100 if usage.total else 0
    trim = _run_command(["systemctl", "is-enabled", "fstrim.timer"], timeout=5)
    trim_enabled = trim is not None and trim.returncode == 0

    summary = f"/home has {free_pct:.1f}% free space."
    details = (
        f"Total: {usage.total / (1024**3):.1f} GiB\n"
        f"Used:  {(usage.total - usage.free) / (1024**3):.1f} GiB\n"
        f"Free:  {usage.free / (1024**3):.1f} GiB\n"
        f"TRIM timer: {'enabled' if trim_enabled else 'disabled'}"
    )
    if free_pct < 15:
        return HardwareProbe("Storage", "warn", summary, details, "Free up space to avoid update and install failures.")
    return HardwareProbe("Storage", "ok", summary, details)
 # _storage_probe

def _platform_probe() -> HardwareProbe:
    virt = _run_command(["systemd-detect-virt"], timeout=5)
    is_vm = virt is not None and virt.returncode == 0
    virt_name = (virt.stdout.strip() or "virtual machine") if is_vm else None

    # Secure Boot state from EFI variable (4-byte attribute header + 1-byte value)
    _SB_VAR = "/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c"
    secure_boot: bool | None = None
    try:
        data = open(_SB_VAR, "rb").read()
        if len(data) >= 5:
            secure_boot = (data[4] == 1)
    except OSError:
        pass

    branch  = _branch_display_name(_current_branch())
    staged  = "yes" if _has_staged_update() else "no"

    if is_vm:
        spice = _run_command(["systemctl", "is-active", "spice-vdagentd.service"], timeout=5)
        spice_active = spice is not None and spice.returncode == 0
        return HardwareProbe(
            "Platform", "dim",
            f"Running inside {virt_name}.",
            (
                f"Environment: {virt_name}\n"
                f"spice-vdagentd: {'active' if spice_active else 'inactive'}\n"
                f"Branch: {branch}\nStaged update: {staged}"
            ),
            "Some gaming and driver checks behave differently in VMs.",
        )

    sb_label = {True: "enabled", False: "disabled", None: "unknown"}.get(secure_boot, "unknown")
    details = f"Branch: {branch}\nStaged update: {staged}\nSecure Boot: {sb_label}"

    if secure_boot:
        return HardwareProbe(
            "Platform", "warn",
            "Bare-metal, Secure Boot enabled — unsigned DKMS modules may not load.",
            details + (
                "\n\nSecure Boot is ON. DKMS modules (xone Xbox dongle, xpadneo Xbox BT)\n"
                "must be signed via MOK to load. If Xbox wireless support is missing,\n"
                "enroll the Machine Owner Key or disable Secure Boot in firmware settings."
            ),
            "If Xbox wireless is missing, check MOK enrollment or disable Secure Boot.",
        )

    return HardwareProbe("Platform", "ok", "Bare-metal environment detected.", details)
 # _platform_probe

