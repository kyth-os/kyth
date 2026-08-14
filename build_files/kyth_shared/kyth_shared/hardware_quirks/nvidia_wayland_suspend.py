"""NVIDIA Wayland suspend quirk — DRM modesetting + preserve VRAM."""
from __future__ import annotations

QUIRK = {
    "id": "nvidia-wayland-suspend",
    "reason": "Enable DRM modesetting and preserve video memory across suspend on the proprietary driver",
    "expires_on": "2027-05-01",
    "provenance": "[policy rationale](hardware-policy.md#managed-quirks)",
    "match": {"pci": [{"vendor": "10de", "classes": ["0300", "0302", "0380"]}]},
    "actions": [
        {"kind": "modprobe", "module": "nvidia-drm", "options": {"modeset": "1"}},
        {"kind": "modprobe", "module": "nvidia", "options": {"NVreg_PreserveVideoMemoryAllocations": "1", "NVreg_TemporaryFilePath": "/var/tmp"}},
    ],
}
