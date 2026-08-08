"""Intel WiFi association power quirk — WPA + BT coexistence."""
from __future__ import annotations

QUIRK = {
    "id": "intel-wifi-association-power",
    "reason": "Keep Intel wireless active during WPA association while preserving Bluetooth coexistence",
    "expires_on": "2027-08-01",
    "provenance": "[policy rationale](hardware-policy.md#managed-quirks)",
    "match": {"pci": [{"vendor": "8086", "drivers": ["iwlwifi"]}]},
    "actions": [
        {"kind": "modprobe", "module": "iwlwifi", "options": {"power_save": "0", "uapsd_disable": "3", "bt_coex_active": "1"}},
        {"kind": "modprobe", "module": "iwlmvm", "options": {"power_scheme": "1"}},
    ],
}
