"""AMDGPU PSR disable quirk — fixes Pageflip timed out on DCN 3.2.1/3.1.2 (7480 + 1681)."""
from __future__ import annotations

QUIRK = {
    "id": "amdgpu-psr-disable",
    "reason": "Disable Display Core PSR on Navi 33 (7480) DCN 3.2.1, Rembrandt 780M (15b9/15bf/15be/164e) DCN 3.1.2/3.1.3 to avoid Pageflip timed out on eDP under Wayland/VRR — TUF A16 Phoenix",
    "expires_on": "2027-08-01",
    "provenance": "https://gitlab.freedesktop.org/drm/amd/-/issues and journalctl amdgpu Pageflip timed out (DCN 3.2.1 on 7480, DCN 3.1.2 eDP-2 PSR 1, TUF A16 15be/164e Phoenix)",
    "match": {"pci": [{"vendor": "1002", "devices": ["7480", "1681", "15bf", "15b9", "15be", "164e"], "classes": ["0300", "0302", "0380"], "drivers": ["amdgpu"]}]},
    "actions": [
        {"kind": "modprobe", "module": "amdgpu", "options": {"dcdebugmask": "0x10"}},
    ],
}
