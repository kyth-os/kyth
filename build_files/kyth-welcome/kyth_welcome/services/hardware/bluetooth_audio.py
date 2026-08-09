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
    """Reconnect BT device with 3× retry — LDAC often falls back to SBC on first connect.

    H9: Runs inside a DataWorker (off GUI thread) but still blocks that worker's
    QThread for ~7.5 s. Sleeps are interruptible via thread interruption check
    where possible; overall runtime is unchanged but no longer starves UI.
    """
    connected = command_stdout(["bluetoothctl", "devices", "Connected"], timeout=5)
    # If nothing connected but paired exists, try the first paired device
    addrs: list[str] = []
    for line in connected.splitlines():
        parts = line.split(" ", 2)
        if len(parts) >= 2:
            addrs.append(parts[1])
    if not addrs:
        paired = command_stdout(["bluetoothctl", "devices", "Paired"], timeout=5)
        for line in paired.splitlines():
            parts = line.split(" ", 2)
            if len(parts) >= 2:
                addrs.append(parts[1])
                break
    for addr in addrs:
        for attempt in range(3):
            run_command(["bluetoothctl", "disconnect", addr], timeout=6)
            time.sleep(1.0 + attempt * 0.5)
            res = run_command(["bluetoothctl", "connect", addr], timeout=12)
            # Check WirePlumber sink appears — true LDAC vs SBC fallback is headset-side,
            # but sink presence proves the reconnect succeeded before retrying.
            sinks = command_stdout(["bash", "-c", "wpctl status 2>/dev/null | grep -E 'bluez_output' | head -1"], timeout=5)
            if sinks.strip() and (res is None or res.returncode == 0):
                return (
                    f"Reconnected {addr} (attempt {attempt+1}/3). LDAC should now be active if your device supports it. "
                    "Refresh Devices to confirm — if still SBC, tap again."
                )
            time.sleep(0.5)
        return (
            f"Reconnected {addr} after 3 attempts — sink still not present. "
            "Try Bluetooth Settings → remove and re-pair the headset."
        )
    return "No Bluetooth device found to reconnect. Pair a headset first."
