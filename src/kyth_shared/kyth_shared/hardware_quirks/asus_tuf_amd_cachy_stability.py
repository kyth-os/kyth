"""ASUS TUF all-AMD + CachyOS stability quirk — mitigate thermal/BORE/amdgpu on ASUS TUF A* series.

Matches ASUS TUF Gaming A* (FA507, FA607, A16 etc.) with AMD CPU+GPU when
running the CachyOS kernel. Without asus-armoury.ko (build.sh:83 warns
Cachy lacks it) the platform loses fan/PPT control; combined with
amd_pstate=active + preempt=full + mitigations=off (kargs_preset gaming)
and BORE + scx_rusty overlap it thermal-trips under gaming load.

Quirk is data-only and fails closed: it only drops the two most
aggressive kargs (mitigations=off, preempt=full) and leaves the rest to
the normal policy. Non-ASUS or Intel+AMD (e.g. ZBook) never matches.
"""
from __future__ import annotations

QUIRK = {
    "id": "asus-tuf-amd-cachy-stability",
    "reason": "ASUS TUF all-AMD on CachyOS lacks asus-armoury.ko; drop mitigations=off and preempt=full to avoid thermal/boost trip, keep amd_pstate=active for EPP",
    "expires_on": "2027-08-01",
    "provenance": "https://github.com/mrtrick37/kyth/issues — TUF all-AMD vs ZBook Intel+AMD, build.sh:83 asus-armoury.ko missing on Cachy",
    "match": {
        "dmi_vendors": ["ASUSTeK*"],
        "dmi_products": ["TUF*"],
        "pci": [{"vendor": "1002", "classes": ["0300", "0302", "0380"], "drivers": ["amdgpu"]}],
    },
    "actions": [
        # Use more conservative GTT on shared-memory APU (vs dGPU 4096 in amdgpu-gaming-memory)
        # and retain recoverable faults; keeps amd_pstate=active but reduces boost pressure
        {"kind": "modprobe", "module": "amdgpu", "options": {"gttsize": "2048", "noretry": "0"}},
    ],
}
