"""Bluetooth USB autosuspend quirk — prevent missed wake traffic."""
from __future__ import annotations

QUIRK = {
    "id": "bluetooth-usb-autosuspend",
    "reason": "Prevent missed remote wake traffic from Bluetooth controllers and low-bandwidth peripherals",
    "expires_on": "2027-08-01",
    "provenance": "[policy rationale](hardware-policy.md#managed-quirks)",
    "match": {"usb": [{"drivers": ["btusb"]}]},
    "actions": [
        {"kind": "modprobe", "module": "btusb", "options": {"enable_autosuspend": "0"}},
    ],
}
