"""MediaTek PCIe WiFi ASPM quirk — mt7921e/mt7925e wake stability."""
from __future__ import annotations

QUIRK = {
    "id": "mediatek-pcie-wifi-aspm",
    "reason": "Avoid intermittent wake and association failures on mt7921e and mt7925e adapters",
    "expires_on": "2027-05-01",
    "provenance": "[policy rationale](hardware-policy.md#managed-quirks)",
    "match": {"pci": [{"vendor": "14c3", "drivers": ["mt7921e", "mt7925e"]}]},
    "actions": [
        {"kind": "modprobe", "module": "mt7921e", "options": {"disable_aspm": "1"}},
        {"kind": "modprobe", "module": "mt7925e", "options": {"disable_aspm": "1"}},
    ],
}
