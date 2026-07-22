"""I/O probes: firmware, connectivity, audio, controllers, peripherals, DisplayLink."""
from __future__ import annotations

import os
import re
import shutil

from .types import HardwareProbe
from ..process import _command_stdout, _run_command
from ..updates import firmware_check_commands
from ..privileged import AuthFrontend, helper_action


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
            action_cmd=(
                helper_action(
                    "xone-dongle-install"
                    if xone_cmd and xone_cmd.endswith("xone-dongle-install")
                    else "xone-firmware-install",
                    frontend=AuthFrontend.PKEXEC,
                ).command()
                if xone_cmd else None
            ),
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
