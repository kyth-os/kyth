"""AMDGPU PSR disable quirk — fixes Pageflip timed out on DCN 3.2.1 7480."""
from __future__ import annotations

QUIRK = {
    "id": "amdgpu-psr-disable",
    "reason": "Disable Display Core PSR on Navi 33 (RX 7600-class, 7480) DCN 3.2.1 to avoid Pageflip timed out under Wayland/VRR",
    "expires_on": "2027-08-01",
    "provenance": "https://gitlab.freedesktop.org/drm/amd/-/issues and journalctl amdgpu Pageflip timed out (DCN 3.2.1)",
    "match": {"pci": [{"vendor": "1002", "devices": ["7480"], "classes": ["0300", "0302", "0380"], "drivers": ["amdgpu"]}]},
    "actions": [
        {"kind": "modprobe", "module": "amdgpu", "options": {"dcdebugmask": "0x10"}},
    ],
}
