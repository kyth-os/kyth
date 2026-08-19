"""Post-migration hardware sanity probes (display, network, printer, BT, power)."""
from __future__ import annotations

import glob
import re

from ..process import command_stdout, run_command, strip_ansi


def hw_display_row() -> tuple[str, str, str] | None:
    out = strip_ansi(command_stdout(["kscreen-doctor", "-o"], timeout=10))
    if not out:
        return None
    hdr = [v.lower() for v in re.findall(r"HDR:\s*([A-Za-z]+)", out)]
    vrr = [v.lower() for v in re.findall(r"VRR:\s*([A-Za-z]+)", out)]
    bits: list[str] = []
    status = "ok"
    if "enabled" in hdr:
        bits.append("HDR is on")
    elif "disabled" in hdr:
        bits.append("your display supports HDR but it's off — enable it in System Settings → Display & Monitor")
        status = "warn"
    elif hdr:
        bits.append("no HDR support advertised by the display")
    if any(v in ("automatic", "always") for v in vrr):
        bits.append("variable refresh rate (FreeSync/G-Sync) is active")
    elif "never" in vrr:
        bits.append("the display supports VRR but it's set to Never — switch it to Automatic for smoother gaming")
        status = "warn"
    elif vrr:
        bits.append("no variable refresh rate support")
    if not bits:
        return None
    joined = "; ".join(bits)
    text = joined[0].upper() + joined[1:] + "."
    if status == "ok" and not any(v == "enabled" for v in hdr) and not any(v in ("automatic", "always") for v in vrr):
        status = "dim"
    return (status, "Display", text)


_hw_display_row = hw_display_row


def collect_hw_sanity() -> list[tuple[str, str, str]]:
    """Things the previous setup configured silently — degrade when tools are missing."""
    rows: list[tuple[str, str, str]] = []

    state = command_stdout(["nmcli", "-t", "-f", "STATE", "general"], timeout=5)
    if state:
        if state.startswith("connected"):
            rows.append(("ok", "Network", "Connected to the internet."))
        else:
            rows.append(("warn", "Network", "Not connected — click the network icon in the system tray to join your Wi-Fi."))

    display = hw_display_row()
    if display:
        rows.append(display)

    lp = run_command(["lpstat", "-p"], timeout=8)
    if lp is not None:
        printers = [ln for ln in lp.stdout.splitlines() if ln.startswith("printer")]
        if printers:
            rows.append(("ok", "Printer", f"{len(printers)} printer{'s' if len(printers) != 1 else ''} configured and ready."))
        else:
            rows.append(("warn", "Printer", "No printers set up yet. Plug one in (or have a network printer on), then run Set Up Printer."))

    rf = command_stdout(["rfkill", "list", "bluetooth"], timeout=5)
    if rf.strip():
        if "soft blocked: yes" in rf.lower() or "hard blocked: yes" in rf.lower():
            rows.append(("warn", "Bluetooth", "Bluetooth is turned off (blocked). Enable it from the system tray or System Settings."))
        else:
            rows.append(("ok", "Bluetooth", "Bluetooth adapter is on. Pair devices from the system tray."))

    if glob.glob("/sys/class/power_supply/BAT*"):
        prof = command_stdout(["powerprofilesctl", "get"], timeout=5)
        if prof:
            rows.append(("ok", "Power", f"Laptop power profile: {prof}. Switch profiles from the battery icon in the tray."))

    return rows


_collect_hw_sanity = collect_hw_sanity
