"""Intel i915 media firmware quirk."""
from __future__ import annotations

QUIRK = {
    "id": "intel-i915-media-firmware",
    "reason": "Enable GuC submission and HuC media firmware on systems still using i915",
    "expires_on": "2027-02-01",
    "provenance": "[policy rationale](hardware-policy.md#managed-quirks)",
    "match": {"pci": [{"vendor": "8086", "classes": ["0300", "0302", "0380"], "drivers": ["i915"]}]},
    "actions": [
        {"kind": "modprobe", "module": "i915", "options": {"enable_guc": "3", "enable_huc": "2"}},
    ],
}
