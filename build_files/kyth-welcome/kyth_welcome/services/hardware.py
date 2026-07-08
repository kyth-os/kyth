import glob
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass

from ..qt import Signal
from ..core_base import (
    TrackedThread, Worker, DataWorker, _run_command, _command_stdout, 
    _is_live_session, _branch_display_name, _current_branch, _has_staged_update
)
from .updates import firmware_check_commands

@dataclass
class HardwareProbe:
    title: str
    status: str
    summary: str
    details: str
    action: str | None = None
    action_page_key: str | None = None
    action_cmd: list[str] | None = None
 # HardwareProbe

class HardwareProbeWorker(TrackedThread):
    done = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            self.done.emit(_collect_hardware_probes())
        except Exception as exc:
            self.failed.emit(str(exc))
 # HardwareProbeWorker

def _detect_nvidia() -> bool:
    try:
        r = subprocess.run(["lspci"], capture_output=True, text=True, timeout=5)
        return "nvidia" in r.stdout.lower()
    except Exception:
        return False
 # _detect_nvidia

def _nvidia_module_loaded() -> bool:
    try:
        r = subprocess.run(["lsmod"], capture_output=True, text=True, timeout=5)
        return "nvidia" in r.stdout.lower()
    except Exception:
        return False
 # _nvidia_module_loaded

def _akmod_nvidia_built() -> bool:
    try:
        r = subprocess.run(["modinfo", "nvidia"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False
 # _akmod_nvidia_built

def _akmod_nvidia_installed() -> bool:
    try:
        r = subprocess.run(["rpm", "-q", "akmod-nvidia"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False
 # _akmod_nvidia_installed

def _hw_setup_service_state() -> str:
    """Returns the systemd active state of kyth-hw-setup.service.
    Possible values: 'activating' (running), 'active' (done), 'failed', 'inactive', or ''."""
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "kyth-hw-setup.service"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip()
    except Exception:
        return ""
 # _hw_setup_service_state

def _hw_setup_done() -> bool:
    return os.path.exists("/var/lib/kyth/hw-setup-done")


def _status_palette(status: str) -> tuple[str, str, str]:
    if status == "ok":
        return ("#121e2d", "#4fc1ff", "OK")
    if status == "warn":
        return ("#152030", "#e0af68", "Warning")
    if status == "err":
        return ("#2b1520", "#f7768e", "Issue")
    return ("#1e1e2e", "#45475a", "Info")


def _gpu_probe(pci_text: str, lsmod_text: str) -> HardwareProbe:
    gpu_lines = [
        line.strip()
        for line in pci_text.splitlines()
        if any(token in line.lower() for token in ("vga compatible controller", "3d controller", "display controller"))
    ]
    if not gpu_lines:
        return HardwareProbe(
            "Graphics", "dim",
            "No GPU information detected.",
            "The helper app could not find a display adapter via lspci.",
        )

    has_nvidia = any("nvidia" in line.lower() for line in gpu_lines)
    has_amd = any("[amd/ati]" in line.lower() or "advanced micro devices" in line.lower() for line in gpu_lines)
    has_intel = any("intel corporation" in line.lower() for line in gpu_lines)
    vendors = [v for v, flag in [("NVIDIA", has_nvidia), ("AMD", has_amd), ("Intel", has_intel)] if flag]
    hybrid = len(vendors) > 1

    if has_nvidia:
        if _nvidia_module_loaded():
            summary = "Hybrid graphics active with NVIDIA drivers." if hybrid else "NVIDIA GPU with active proprietary drivers."
            return HardwareProbe("Graphics", "ok", summary, "Detected:\n" + "\n".join(gpu_lines))
        if _akmod_nvidia_built():
            return HardwareProbe(
                "Graphics", "warn",
                "NVIDIA drivers installed but not yet active.",
                "The nvidia module exists for this kernel but is not loaded.\nDetected:\n" + "\n".join(gpu_lines),
                "Reboot to activate the staged driver.",
                action_page_key="NVIDIA",
            )
        summary = "Hybrid graphics: NVIDIA driver not active." if hybrid else "NVIDIA hardware found without an active driver."
        return HardwareProbe(
            "Graphics", "err", summary,
            "Detected:\n" + "\n".join(gpu_lines),
            "Open NVIDIA Drivers to build and stage the driver.",
            action_page_key="NVIDIA",
        )

    if has_amd:
        loaded = "amdgpu" in lsmod_text.lower()
        status = "ok" if loaded else "warn"
        summary = "AMD GPU — amdgpu driver loaded." if loaded else "AMD GPU — amdgpu driver not found in lsmod."
        return HardwareProbe("Graphics", status, summary, "Detected:\n" + "\n".join(gpu_lines))

    if has_intel:
        loaded = "i915" in lsmod_text.lower() or "\nxe " in f"\n{lsmod_text.lower()}"
        status = "ok" if loaded else "warn"
        summary = "Intel GPU — kernel driver loaded." if loaded else "Intel GPU — no kernel driver found in lsmod."
        return HardwareProbe("Graphics", status, summary, "Detected:\n" + "\n".join(gpu_lines))

    return HardwareProbe("Graphics", "dim", "GPU detected, vendor not recognized.", "Detected:\n" + "\n".join(gpu_lines))
 # _gpu_probe

def _firmware_probe() -> HardwareProbe:
    devices = _run_command(["fwupdmgr", "get-devices"], timeout=15)
    if devices is None:
        return HardwareProbe("Firmware", "dim", "fwupd not available.", "Install fwupd to inspect firmware-managed devices.")
    if devices.returncode != 0:
        return HardwareProbe(
            "Firmware", "warn",
            "Firmware tooling installed but device enumeration failed.",
            devices.stdout.strip() or "fwupdmgr get-devices exited with an error.",
        )

    device_count = devices.stdout.count("Device ID:")
    refresh_cmd, updates_cmd = firmware_check_commands(refresh=True)
    _run_command(refresh_cmd, timeout=60)
    updates = _run_command(updates_cmd, timeout=20)
    if updates is not None and updates.returncode == 0:
        return HardwareProbe(
            "Firmware", "warn",
            f"Firmware updates available for {device_count or 'one or more'} device(s).",
            updates.stdout.strip() or devices.stdout.strip(),
        )
    if updates is not None and updates.returncode == 2:
        return HardwareProbe(
            "Firmware", "ok",
            f"fwupd managing {device_count} device(s), no pending updates.",
            devices.stdout.strip(),
        )
    return HardwareProbe(
        "Firmware", "dim",
        f"fwupd available, {device_count} managed device(s).",
        devices.stdout.strip(),
    )
 # _firmware_probe

def _connectivity_probe(pci_text: str, usb_text: str) -> HardwareProbe:
    combined = "\n".join([pci_text.lower(), usb_text.lower()])
    wifi_present = any(token in combined for token in ("network controller", "wireless", "wi-fi", "802.11", "wlan"))
    bluetooth_present = "bluetooth" in combined
    rfkill = _command_stdout(["rfkill", "list"], timeout=5)
    nmcli = _command_stdout(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"], timeout=5)

    blocked = []
    if rfkill:
        lines = rfkill.lower().splitlines()
        if any("soft blocked: yes" in l for l in lines):
            blocked.append("soft-blocked")
        if any("hard blocked: yes" in l for l in lines):
            blocked.append("hard-blocked")

    wifi_states = [l for l in nmcli.splitlines() if ":wifi:" in l]

    parts = []
    if wifi_present:
        parts.append("Wi-Fi")
    if bluetooth_present:
        parts.append("Bluetooth")

    if not parts:
        return HardwareProbe(
            "Connectivity", "dim",
            "No Wi-Fi or Bluetooth hardware detected.",
            "Expected on desktops or virtual machines.",
        )

    details = []
    if wifi_states:
        details.append("NetworkManager:\n" + "\n".join(wifi_states))
    if rfkill:
        details.append("rfkill:\n" + rfkill)

    if blocked:
        return HardwareProbe(
            "Connectivity", "warn",
            f"{', '.join(parts)} detected but radio is {', '.join(blocked)}.",
            "\n\n".join(details) or "rfkill reports blocked radios.",
            "Enable Wireless",
            action_cmd=["rfkill", "unblock", "all"],
        )

    return HardwareProbe(
        "Connectivity", "ok",
        f"{', '.join(parts)} hardware detected and ready.",
        "\n\n".join(details) or "Wireless hardware looks healthy.",
    )
 # _connectivity_probe

def _audio_probe() -> HardwareProbe:
    pipewire = _run_command(["systemctl", "--user", "is-active", "pipewire.service"], timeout=5)
    wireplumber = _run_command(["systemctl", "--user", "is-active", "wireplumber.service"], timeout=5)
    pactl_info = _run_command(["pactl", "info"], timeout=5)
    sinks = _command_stdout(["pactl", "list", "short", "sinks"], timeout=5)
    sink_count = len([l for l in sinks.splitlines() if l.strip()])

    if pactl_info is None:
        return HardwareProbe("Audio", "dim", "Audio inspection tools not available.", "Could not query pactl.")

    if pactl_info.returncode != 0:
        return HardwareProbe(
            "Audio", "warn",
            "PipeWire is not responding to pactl.",
            pactl_info.stdout.strip() or "pactl info returned a non-zero exit code.",
            "Log out and back in, then refresh.",
        )

    services = []
    if pipewire is not None and pipewire.returncode == 0:
        services.append("pipewire")
    if wireplumber is not None and wireplumber.returncode == 0:
        services.append("wireplumber")

    if sink_count == 0:
        return HardwareProbe(
            "Audio", "warn",
            "Audio services running but no playback sinks detected.",
            (pactl_info.stdout.strip() + "\n\nSinks:\n" + (sinks or "none")).strip(),
            "Reconnect audio hardware or inspect your session config.",
        )

    return HardwareProbe(
        "Audio", "ok",
        f"Audio stack healthy — {sink_count} playback sink(s).",
        ("Services: " + ", ".join(services) + "\n\n" if services else "") + pactl_info.stdout.strip(),
    )
 # _audio_probe

def _controller_probe(usb_text: str, lsmod_text: str) -> HardwareProbe:
    _GAMING_VIDS: dict[str, str] = {
        "045e": "Xbox",
        "054c": "PlayStation",
        "057e": "Nintendo",
        "2dc8": "8BitDo",
        "0f0d": "HORI",
        "28de": "Valve",
        "20d6": "PowerA",
        "0e6f": "PDP",
    }
    _XONE_DONGLE_PIDS = {"02e6", "02fe"}
    _DUALSENSE_PIDS   = {"0ce6", "0df2"}
    _DS4_PIDS         = {"05c4", "09cc", "0ba0"}

    usb_controllers: list[str] = []
    xone_dongle     = False
    dualsense_found = False

    for line in usb_text.splitlines():
        m = re.search(r"ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)", line)
        if not m:
            continue
        vid, pid, desc = m.group(1).lower(), m.group(2).lower(), m.group(3).strip()
        if vid not in _GAMING_VIDS:
            continue
        if vid == "045e" and pid in _XONE_DONGLE_PIDS:
            xone_dongle = True
            usb_controllers.append("Xbox Wireless USB Dongle")
        elif vid == "054c" and pid in _DUALSENSE_PIDS:
            dualsense_found = True
            usb_controllers.append("PlayStation DualSense")
        elif vid == "054c" and pid in _DS4_PIDS:
            usb_controllers.append("PlayStation DualShock 4")
        else:
            usb_controllers.append(desc or f"{_GAMING_VIDS[vid]} controller")

    # /dev/input/by-id catches Bluetooth controllers and anything lsusb missed
    input_nodes: list[str] = []
    try:
        for name in sorted(os.listdir("/dev/input/by-id")):
            if any(tok in name.lower() for tok in ("joystick", "gamepad", "controller")):
                input_nodes.append(name)
    except OSError:
        pass

    lsmod_norm = lsmod_text.lower().replace("-", "_")
    xone_loaded    = "xone_hid"      in lsmod_norm
    xpadneo_loaded = "xpadneo"       in lsmod_norm
    hid_ps_loaded  = "hid_playstation" in lsmod_norm

    if not usb_controllers and not input_nodes:
        return HardwareProbe(
            "Controllers", "dim",
            "No gaming controllers detected.",
            (
                "Supported out of the box: Xbox (USB wired/wireless dongle), PlayStation\n"
                "DualSense / DualShock 4, Nintendo Switch Pro, 8BitDo, and most USB or\n"
                "Bluetooth HID controllers.\n\n"
                "Connect a controller and press Refresh."
            ),
        )

    details_parts: list[str] = []
    if usb_controllers:
        details_parts.append("USB devices:\n" + "\n".join(f"  {c}" for c in usb_controllers))
    if input_nodes:
        details_parts.append("Input nodes:\n" + "\n".join(f"  {n}" for n in input_nodes))
    active_mods = [label for label, flag in [
        ("xpadneo (Xbox BT)",       xpadneo_loaded),
        ("xone_hid (Xbox dongle)",  xone_loaded),
        ("hid_playstation (PS4/5)", hid_ps_loaded),
    ] if flag]
    if active_mods:
        details_parts.append("Active modules: " + ", ".join(active_mods))
    details = "\n\n".join(details_parts)

    # Xbox wireless dongle present but xone module not active → firmware step needed
    if xone_dongle and not xone_loaded:
        xone_cmd = shutil.which("xone-dongle-install") or shutil.which("xone-firmware-install")
        firmware_hint = (
            f"Run:  sudo {xone_cmd}" if xone_cmd
            else "Run:  sudo xone-dongle-install"
        )
        return HardwareProbe(
            "Controllers", "warn",
            "Xbox Wireless USB Dongle detected — firmware setup required before controllers can pair.",
            (
                details + "\n\n"
                "The xone kernel module is installed but the dongle has not been flashed with\n"
                "Microsoft's firmware. Xbox wireless controllers cannot connect until this step\n"
                "is complete.\n\n" + firmware_hint
            ),
            "Install Xbox dongle firmware (opens password prompt)",
            action_cmd=(["pkexec", xone_cmd] if xone_cmd else None),
        )

    n = len(usb_controllers) or len(input_nodes)
    summary = f"{n} controller{'s' if n != 1 else ''} detected and ready."
    if dualsense_found:
        if shutil.which("dualsensectl"):
            summary += " DualSense haptics and adaptive triggers available via dualsensectl."
        else:
            summary += " DualSense connected — adaptive triggers and haptics work in supported games."

    return HardwareProbe("Controllers", "ok", summary, details)
 # _controller_probe

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

def _peripheral_probe(usb_text: str) -> HardwareProbe:
    _GAMING_VIDS: dict[str, str] = {
        "1532": "Razer",
        "1b1c": "Corsair",
        "1038": "SteelSeries",
        "046d": "Logitech",
        "0b05": "ASUS ROG",
        "1e7d": "Roccat",
        "0951": "HyperX",
        "187c": "Alienware",
        "10f5": "Turtle Beach",
        "0fd9": "Elgato",
        "20a0": "Wooting",
    }

    found: dict[str, list[str]] = {}
    razer_found = False

    for line in usb_text.splitlines():
        m = re.search(r"ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)", line)
        if not m:
            continue
        vid, _pid, desc = m.group(1).lower(), m.group(2).lower(), m.group(3).strip()
        if vid not in _GAMING_VIDS:
            continue
        vendor = _GAMING_VIDS[vid]
        found.setdefault(vendor, []).append(desc or f"{vendor} device")
        if vid == "1532":
            razer_found = True

    if not found:
        return HardwareProbe(
            "Peripherals", "dim",
            "No gaming peripherals detected.",
            (
                "Supported: Razer (via OpenRazer), Corsair, SteelSeries, Logitech G,\n"
                "ASUS ROG, Roccat, HyperX, Wooting, Elgato, and Alienware.\n\n"
                "Connect peripherals via USB and press Refresh."
            ),
        )

    details_parts: list[str] = []
    for vendor, devices in sorted(found.items()):
        details_parts.append(f"{vendor}:\n" + "\n".join(f"  {d}" for d in devices))

    action_label: str | None = None
    action_cmd: list[str] | None = None

    if razer_found:
        r = _run_command(["systemctl", "--user", "is-active", "openrazer-daemon.service"], timeout=5)
        daemon_active = r is not None and r.returncode == 0
        if daemon_active:
            details_parts.append("OpenRazer daemon: active — RGB and DPI controls ready.")
        else:
            details_parts.append("OpenRazer daemon: not running — RGB and DPI controls unavailable.")
            action_label = "Start OpenRazer daemon"
            action_cmd = ["systemctl", "--user", "start", "openrazer-daemon.service"]

    n = sum(len(v) for v in found.values())
    vendors = list(found.keys())
    if len(vendors) == 1:
        summary = f"{n} {vendors[0]} device{'s' if n > 1 else ''} detected."
    else:
        summary = f"{n} gaming peripherals detected: {', '.join(vendors)}."

    if action_label:
        return HardwareProbe(
            "Peripherals", "warn",
            summary + " OpenRazer daemon not running.",
            "\n\n".join(details_parts),
            action_label,
            action_cmd=action_cmd,
        )

    return HardwareProbe("Peripherals", "ok", summary, "\n\n".join(details_parts))
 # _peripheral_probe

def _displaylink_probe(usb_text: str, lsmod_text: str) -> HardwareProbe:
    found_desc: str | None = None
    for line in usb_text.splitlines():
        m = re.search(r"ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)", line)
        if not m:
            continue
        vid, _pid, desc = m.group(1).lower(), m.group(2).lower(), m.group(3).strip()
        if vid == "17e9":
            found_desc = desc or "DisplayLink dock/adapter"
            break

    if not found_desc:
        return HardwareProbe(
            "DisplayLink dock", "dim",
            "No DisplayLink dock or adapter detected.",
            (
                "DisplayLink USB/USB-C docks let you drive extra monitors from a "
                "single port. Connect one and press Refresh."
            ),
        )

    if re.search(r"^evdi\s", lsmod_text, re.MULTILINE):
        return HardwareProbe(
            "DisplayLink dock", "ok",
            f"{found_desc} connected — driver active.",
            "The evdi kernel module is loaded; extra displays through this dock should work.",
        )

    return HardwareProbe(
        "DisplayLink dock", "warn",
        f"{found_desc} detected, but the driver is not installed.",
        (
            "The evdi kernel module isn't loaded, so extra monitors on this dock "
            "won't show video.\n\nRun `ujust install-displaylink` in a terminal to "
            "install and sign the evdi driver, then reboot."
        ),
    )
 # _displaylink_probe

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

def _vaapi_failure_summary(output: str) -> tuple[str, str]:
    lowered = output.lower()

    if "permission denied" in lowered or "failed to open render node" in lowered:
        return (
            "VA-API cannot access the GPU render device.",
            "Confirm your user has render/video device access, then sign out and back in.",
        )

    if "radeonsi_drv_video.so" in lowered and (
        "resource allocation failed" in lowered
        or "init failed" in lowered
        or "va_openDriver() returns 2" in output
    ):
        return (
            "AMD VA-API driver was found but could not initialize.",
            "Reboot after Mesa/GPU driver updates; if it persists, verify mesa-dri-drivers provides mesa-va-drivers and check Graphics for amdgpu status.",
        )

    if "failed to open" in lowered or "driver_name" in lowered or "va_openDriver" in output:
        return (
            "VA-API driver could not be opened.",
            "Verify the matching VA-API driver package is installed for this GPU and no stale LIBVA_DRIVER_NAME override is set.",
        )

    return (
        "VA-API initialisation failed.",
        "Confirm your GPU driver is loaded (see Graphics).",
    )
 # _vaapi_failure_summary

def _mesa_vaapi_failure_context() -> tuple[str, str]:
    rpm = _run_command([
        "rpm",
        "-q",
        "--queryformat",
        "%{NAME} %{VERSION}-%{RELEASE}.%{ARCH}\n%{VENDOR}\n%{PACKAGER}\n",
        "mesa-dri-drivers",
        "mesa-vulkan-drivers",
        "libva",
    ], timeout=5)
    if rpm is None or rpm.returncode != 0:
        return "", ""

    details = rpm.stdout.strip()
    lowered = details.lower()
    if "negativo17" in lowered or "fedora-multimedia" in lowered:
        return (
            details,
            "Mesa/libva is installed from negativo17's fedora-multimedia repo; distro-sync the Mesa stack back to Fedora/RPM Fusion packages, then reboot.",
        )

    if "xxmitsu" in lowered or "copr" in lowered:
        return (
            details,
            "Mesa is installed from the mesa-git COPR; switch back to stable Fedora Mesa or wait for a fixed mesa-git snapshot.",
        )

    return details, ""
 # _mesa_vaapi_failure_context

def _compact_vaapi_failure_details(primary_output: str, direct_probe_details: list[str]) -> str:
    attempts = [("$ vainfo", primary_output.strip())]
    for detail in direct_probe_details:
        command, _, probe_output = detail.partition("\n")
        attempts.append((command.strip(), probe_output.strip()))

    attempt_lines = []
    drivers = []
    errors = []
    for command, probe_output in attempts:
        if not probe_output:
            continue
        display_match = re.search(r"Trying display:\s*([^\n]+)", probe_output)
        display = display_match.group(1).strip() if display_match else "default display"
        attempt_lines.append(f"{command}: {display}")

        for driver in re.findall(r"Trying to open\s+([^\s]+)", probe_output):
            if driver not in drivers:
                drivers.append(driver)

        for line in probe_output.splitlines():
            normalized = line.strip()
            lowered = normalized.lower()
            if (
                "error:" in lowered
                or "failed with error code" in lowered
                or "va_opendriver()" in lowered
            ) and normalized not in errors:
                errors.append(normalized)

    lines = []
    if attempt_lines:
        lines.append("Probe attempts:")
        lines.extend(f"- {attempt}" for attempt in attempt_lines)
    if drivers:
        lines.extend(["", "VA-API driver:"])
        lines.extend(f"- {driver}" for driver in drivers)
    if errors:
        lines.extend(["", "Failure reported:"])
        lines.extend(f"- {error}" for error in errors[:5])

    if not lines:
        return primary_output.strip()
    return "\n".join(lines)
 # _compact_vaapi_failure_details

def _vaapi_profiles(output: str) -> list[str]:
    lowered = output.lower()
    profiles = []
    if "h264" in lowered or "avc" in lowered:
        profiles.append("H.264")
    if "h265" in lowered or "hevc" in lowered:
        profiles.append("H.265")
    if "av1" in lowered:
        profiles.append("AV1")
    if "vp9" in lowered:
        profiles.append("VP9")
    if "vp8" in lowered:
        profiles.append("VP8")
    return profiles
 # _vaapi_profiles

def _successful_vaapi_probe(vainfo: subprocess.CompletedProcess[str] | None) -> tuple[list[str], str] | None:
    if vainfo is None:
        return None
    output = (vainfo.stdout + vainfo.stderr).strip()
    if vainfo.returncode != 0:
        return None
    profiles = _vaapi_profiles(output)
    if not profiles:
        return None
    return profiles, output
 # _successful_vaapi_probe

def _codec_probe() -> HardwareProbe:
    sw_driver = (
        os.environ.get("MESA_LOADER_DRIVER_OVERRIDE", "")
        or os.environ.get("GALLIUM_DRIVER", "")
    )
    if "llvmpipe" in sw_driver.lower():
        env_lines = "\n".join(
            f"{k}={os.environ[k]}"
            for k in ("MESA_LOADER_DRIVER_OVERRIDE", "GALLIUM_DRIVER", "LIBGL_ALWAYS_SOFTWARE")
            if k in os.environ
        )
        skel_file = os.path.expanduser("~/.config/plasma-workspace/env/10-kyth-qemu-safe.sh")
        source = skel_file if os.path.exists(skel_file) else "~/.config/plasma-workspace/env/"
        return HardwareProbe(
            "Video Decode", "warn",
            "Software rendering is active in this session — VA-API requires hardware GPU access.",
            f"{env_lines}\n\nSet by {source} (QEMU compatibility fallback active on bare metal).",
            f"Delete {skel_file} and log out/in to restore hardware rendering.",
        )

    vainfo = _run_command(["vainfo"], timeout=10)
    if vainfo is None:
        return HardwareProbe(
            "Video Decode", "dim",
            "vainfo not available — cannot check VA-API support.",
            "Install libva-utils to inspect hardware video decode capabilities.",
        )

    direct_probe_details = []
    successful = _successful_vaapi_probe(vainfo)
    if successful is None:
        render_nodes = sorted(glob.glob("/dev/dri/renderD*"))
        for node in render_nodes:
            drm_vainfo = _run_command(["vainfo", "--display", "drm", "--device", node], timeout=10)
            if drm_vainfo is not None:
                direct_probe_details.append(
                    f"$ vainfo --display drm --device {node}\n"
                    f"{(drm_vainfo.stdout + drm_vainfo.stderr).strip()}"
                )
            successful = _successful_vaapi_probe(drm_vainfo)
            if successful is not None:
                profiles, drm_output = successful
                details = [
                    "$ vainfo",
                    (vainfo.stdout + vainfo.stderr).strip(),
                    f"$ vainfo --display drm --device {node}",
                    drm_output,
                ]
                return HardwareProbe(
                    "Video Decode", "ok",
                    f"VA-API hardware decode: {', '.join(profiles)}.",
                    "\n\n".join(part for part in details if part),
                )
    else:
        profiles, output = successful
        return HardwareProbe(
            "Video Decode", "ok",
            f"VA-API hardware decode: {', '.join(profiles)}.",
            output,
        )

    output = (vainfo.stdout + vainfo.stderr)
    if vainfo.returncode != 0 and "failed" in output.lower():
        summary, recommendation = _vaapi_failure_summary(output)
        details = _compact_vaapi_failure_details(output, direct_probe_details)
        mesa_details, mesa_recommendation = _mesa_vaapi_failure_context()
        if mesa_details:
            details = f"{details}\n\nMesa package:\n{mesa_details}"
        if mesa_recommendation:
            recommendation = mesa_recommendation
        return HardwareProbe(
            "Video Decode", "warn",
            summary,
            details,
            recommendation,
        )

    profiles = _vaapi_profiles(output)
    if not profiles:
        return HardwareProbe(
            "Video Decode", "warn",
            "VA-API is available but no recognised decode profiles were found.",
            (vainfo.stdout + vainfo.stderr).strip(),
        )

    return HardwareProbe(
        "Video Decode", "ok",
        f"VA-API hardware decode: {', '.join(profiles)}.",
        (vainfo.stdout + vainfo.stderr).strip(),
    )
 # _codec_probe

def _collect_hardware_probes() -> list[HardwareProbe]:
    from .diagnostics import _system_hub_probe
    pci_text  = _command_stdout(["lspci"],  timeout=5)
    usb_text  = _command_stdout(["lsusb"],  timeout=5)
    lsmod_text = _command_stdout(["lsmod"], timeout=5)
    return [
        # Gaming-critical first
        _gpu_probe(pci_text, lsmod_text),
        _cpu_probe(),
        _display_probe(),
        _memory_probe(),
        # Input devices
        _controller_probe(usb_text, lsmod_text),
        _peripheral_probe(usb_text),
        _displaylink_probe(usb_text, lsmod_text),
        # System health
        _audio_probe(),
        _thermal_probe(),
        _connectivity_probe(pci_text, usb_text),
        _codec_probe(),
        _firmware_probe(),
        _storage_probe(),
        _platform_probe(),
        _system_hub_probe(),
    ]
 # _collect_hardware_probes

def _find_ntfs_drives() -> list[dict]:
    """Return other system NTFS and locked BitLocker partitions visible to lsblk."""
    try:
        r = subprocess.run(
            ["lsblk", "--json", "--output", "NAME,FSTYPE,SIZE,LABEL,MOUNTPOINT,PATH"],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(r.stdout)
    except Exception:
        return []

    results: list[dict] = []

    def _walk(devices: list):
        for dev in devices:
            if not isinstance(dev, dict):
                continue
            fstype = (dev.get("fstype") or "").lower()
            if fstype in ("ntfs", "ntfs3", "bitlocker"):
                name = dev.get("name") or ""
                path = dev.get("path") or (f"/dev/{name}" if name else "")
                if not path:
                    continue
                results.append({
                    "dev":   path,
                    "name":  name,
                    "size":  dev.get("size", "?"),
                    "label": dev.get("label") or "",
                    "mount": dev.get("mountpoint") or "",
                    "is_bitlocker": fstype == "bitlocker",
                })
            _walk(dev.get("children") or [])

    _walk(data.get("blockdevices", []))
    return results
 # _find_ntfs_drives

def _detect_controllers() -> dict:
    """Snapshot of all connected controllers and driver state. Thread-safe."""
    usb_text = _command_stdout(["lsusb"], timeout=6)
    lsmod_text = _command_stdout(["lsmod"], timeout=4)

    _GAMING_VIDS: dict[str, str] = {
        "045e": "Xbox", "054c": "PlayStation", "057e": "Nintendo",
        "2dc8": "8BitDo", "0f0d": "HORI", "28de": "Valve",
        "20d6": "PowerA", "0e6f": "PDP",
    }
    _XONE_DONGLE_PIDS = {"02e6", "02fe"}
    _DUALSENSE_PIDS   = {"0ce6", "0df2"}
    _DS4_PIDS         = {"05c4", "09cc", "0ba0"}
    _SWITCH_PRO_PID   = "2009"

    usb_controllers: list[tuple[str, str]] = []   # (display_name, type_key)
    xone_dongle = False
    dualsense_found = False
    ds4_found = False
    switch_pro_found = False

    for line in usb_text.splitlines():
        m = re.search(r"ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)", line)
        if not m:
            continue
        vid, pid, desc = m.group(1).lower(), m.group(2).lower(), m.group(3).strip()
        if vid not in _GAMING_VIDS:
            continue
        if vid == "045e" and pid in _XONE_DONGLE_PIDS:
            xone_dongle = True
            usb_controllers.append(("Xbox Wireless USB Dongle", "xbox_dongle"))
        elif vid == "054c" and pid in _DUALSENSE_PIDS:
            dualsense_found = True
            usb_controllers.append(("PlayStation 5 DualSense", "dualsense"))
        elif vid == "054c" and pid in _DS4_PIDS:
            ds4_found = True
            usb_controllers.append(("PlayStation 4 DualShock 4", "ds4"))
        elif vid == "057e" and pid == _SWITCH_PRO_PID:
            switch_pro_found = True
            usb_controllers.append(("Nintendo Switch Pro Controller", "switch_pro"))
        else:
            usb_controllers.append((desc or f"{_GAMING_VIDS[vid]} controller", "generic"))

    input_nodes: list[str] = []
    try:
        for name in sorted(os.listdir("/dev/input/by-id")):
            if any(t in name.lower() for t in ("joystick", "gamepad", "controller")):
                input_nodes.append(name)
    except OSError:
        pass

    lsmod_norm = lsmod_text.lower().replace("-", "_")

    dualsensectl_out = ""
    if dualsense_found and shutil.which("dualsensectl"):
        dualsensectl_out = _command_stdout(["dualsensectl", "status", "0"], timeout=3)

    # Secure Boot state
    secure_boot = False
    try:
        for ef in os.listdir("/sys/firmware/efi/efivars"):
            if ef.startswith("SecureBoot-"):
                data = open(f"/sys/firmware/efi/efivars/{ef}", "rb").read()
                secure_boot = len(data) >= 5 and data[4] == 1
                break
    except OSError:
        pass

    return {
        "usb_controllers":  usb_controllers,
        "input_nodes":      input_nodes,
        "xone_dongle":      xone_dongle,
        "xone_loaded":      "xone_hid"       in lsmod_norm,
        "xpadneo_loaded":   "xpadneo"        in lsmod_norm,
        "hid_ps_loaded":    "hid_playstation" in lsmod_norm,
        "dualsense_found":  dualsense_found,
        "ds4_found":        ds4_found,
        "switch_pro_found": switch_pro_found,
        "dualsensectl_out": dualsensectl_out,
        "secure_boot":      secure_boot,
        "jstest_available": bool(shutil.which("jstest-gtk")),
    }
 # _detect_controllers
