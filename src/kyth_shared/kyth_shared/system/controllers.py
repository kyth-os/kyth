"""Pure controller detection shared by the probe daemon and System Hub."""
from __future__ import annotations

import os
import re
import shutil

from .process import command_stdout

_GAMING_VIDS = {
    "045e": "Xbox", "054c": "PlayStation", "057e": "Nintendo",
    "2dc8": "8BitDo", "0f0d": "HORI", "28de": "Valve",
    "20d6": "PowerA", "0e6f": "PDP",
}
_XONE_DONGLE_PIDS = {"02e6", "02fe"}
_DUALSENSE_PIDS = {"0ce6", "0df2"}
_DS4_PIDS = {"05c4", "09cc", "0ba0"}


def detect_controllers() -> dict:
    """Return connected controller and driver state without UI dependencies."""
    usb_text = command_stdout(["lsusb"], timeout=6)
    lsmod_text = command_stdout(["lsmod"], timeout=4)
    usb_controllers: list[tuple[str, str]] = []
    xone_dongle = dualsense_found = ds4_found = switch_pro_found = False

    for line in usb_text.splitlines():
        match = re.search(r"ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)", line)
        if not match:
            continue
        vid, pid, description = match.group(1).lower(), match.group(2).lower(), match.group(3).strip()
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
        elif vid == "057e" and pid == "2009":
            switch_pro_found = True
            usb_controllers.append(("Nintendo Switch Pro Controller", "switch_pro"))
        else:
            usb_controllers.append((description or f"{_GAMING_VIDS[vid]} controller", "generic"))

    try:
        input_nodes = [
            name for name in sorted(os.listdir("/dev/input/by-id"))
            if any(token in name.lower() for token in ("joystick", "gamepad", "controller"))
        ]
    except OSError:
        input_nodes = []

    dualsensectl_out = ""
    if dualsense_found and shutil.which("dualsensectl"):
        dualsensectl_out = command_stdout(["dualsensectl", "status", "0"], timeout=3)

    secure_boot = False
    try:
        for entry in os.listdir("/sys/firmware/efi/efivars"):
            if entry.startswith("SecureBoot-"):
                with open(f"/sys/firmware/efi/efivars/{entry}", "rb") as stream:
                    data = stream.read()
                secure_boot = len(data) >= 5 and data[4] == 1
                break
    except OSError:
        pass

    modules = lsmod_text.lower().replace("-", "_")
    return {
        "usb_controllers": usb_controllers,
        "input_nodes": input_nodes,
        "xone_dongle": xone_dongle,
        "xone_loaded": "xone_hid" in modules,
        "xpadneo_loaded": "xpadneo" in modules,
        "hid_ps_loaded": "hid_playstation" in modules,
        "dualsense_found": dualsense_found,
        "ds4_found": ds4_found,
        "switch_pro_found": switch_pro_found,
        "dualsensectl_out": dualsensectl_out,
        "secure_boot": secure_boot,
        "jstest_available": bool(shutil.which("jstest-gtk")),
    }
