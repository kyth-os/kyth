"""NTFS/BitLocker drive listing and controller detection snapshot."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from ..process import _command_stdout, _probe_cached


def _find_ntfs_drives() -> list[dict]:
    """Return other system NTFS and locked BitLocker partitions visible to lsblk."""
    try:
        r = subprocess.run(
            ["lsblk", "--json", "--output", "NAME,FSTYPE,SIZE,LABEL,MOUNTPOINT,PATH"],
            capture_output=True, text=True, timeout=10, check=False,
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
    def fetch() -> dict:
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
                    with open(f"/sys/firmware/efi/efivars/{ef}", "rb") as fh:
                        data = fh.read()
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
    return _probe_cached("controllers-detect", 5.0, fetch)
 # _detect_controllers
