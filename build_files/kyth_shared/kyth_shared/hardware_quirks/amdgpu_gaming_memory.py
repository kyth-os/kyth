"""AMDGPU gaming memory quirk — PowerPlay + GTT bounding."""
from __future__ import annotations

QUIRK = {
    "id": "amdgpu-gaming-memory",
    "reason": "Expose PowerPlay controls while bounding APU GTT pressure and retaining recoverable VM fault handling",
    "expires_on": "2027-08-01",
    "provenance": "[policy rationale](hardware-policy.md#managed-quirks)",
    "match": {"pci": [{"vendor": "1002", "classes": ["0300", "0302", "0380"], "drivers": ["amdgpu"]}]},
    "actions": [
        {"kind": "modprobe", "module": "amdgpu", "options": {"ppfeaturemask": "0xffffffff", "gttsize": "4096", "noretry": "0"}},
    ],
}
