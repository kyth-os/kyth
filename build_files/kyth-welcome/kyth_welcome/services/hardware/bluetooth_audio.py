"""Bluetooth audio helpers (codec reconnect, default sink switch)."""
from __future__ import annotations

import time

from ..process import command_stdout, run_command


def bt_audio_device_summary() -> str:
    paired = command_stdout(["bluetoothctl", "devices", "Paired"], timeout=5)
    connected = command_stdout(["bluetoothctl", "devices", "Connected"], timeout=5)
    connected_addrs = {
        line.split()[1] for line in connected.splitlines()
        if len(line.split()) >= 2
    }
    sinks_raw = command_stdout(
        ["bash", "-c", "wpctl status 2>/dev/null | grep -E 'bluez_output' | head -8"],
        timeout=5,
    )
    lines: list[str] = []
    for line in paired.splitlines():
        parts = line.split(" ", 2)
        if len(parts) < 3:
            continue
        addr, name = parts[1], parts[2]
        state = "Connected" if addr in connected_addrs else "Paired (not connected)"
        lines.append(f"{name}  [{addr}]  —  {state}")
    if sinks_raw.strip():
        lines.append(f"\nWirePlumber BT sinks:\n{sinks_raw.strip()}")
    return "\n".join(lines) if lines else (
        "No paired Bluetooth devices found. Pair a headset via Bluetooth Settings."
    )


def switch_to_bt_audio_output() -> str:
    result = run_command(
        [
            "bash", "-c",
            "wpctl status 2>/dev/null | grep -E '\\bbluez_output' | head -1"
            " | awk '{print $1}' | tr -d '.*'",
        ],
        timeout=5,
    )
    sink_id = (result.stdout.strip() if result else "")
    if sink_id:
        run_command(["wpctl", "set-default", sink_id], timeout=5)
        return (
            f"Audio output switched to Bluetooth device (WirePlumber ID: {sink_id}). "
            "If the change doesn't take effect, log out and back in."
        )
    return "No Bluetooth audio output found. Make sure your headset is connected, then refresh."


def force_ldac_reconnect() -> str:
    connected = command_stdout(["bluetoothctl", "devices", "Connected"], timeout=5)
    for line in connected.splitlines():
        parts = line.split(" ", 2)
        if len(parts) < 2:
            continue
        addr = parts[1]
        run_command(["bluetoothctl", "disconnect", addr], timeout=6)
        time.sleep(1.5)
        run_command(["bluetoothctl", "connect", addr], timeout=12)
        return (
            f"Reconnected {addr}. LDAC should now be active if your device supports it. "
            "Refresh Devices to confirm the WirePlumber sink is present."
        )
    return ""
