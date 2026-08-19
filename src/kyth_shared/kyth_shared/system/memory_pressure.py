"""Memory pressure helper — Cachy zram parity (N39)."""
from __future__ import annotations
import subprocess

from kyth_shared.commands import run

def memory_pressure_options() -> dict[str, str]:
    return {"swappiness": "vm.swappiness", "zram": "zram0"}

def apply_swappiness(value: int, dry_run: bool = False) -> tuple[bool, str]:
    if not 0 <= value <= 100:
        return False, "swappiness 0-100"
    if dry_run:
        return True, f"dry-run ok: swappiness {value}"
    try:
        r = run(["sysctl", "-w", f"vm.swappiness={value}"], capture_output=True, text=True, timeout=5, check=False)
        return (r.returncode == 0, r.stdout.strip() or r.stderr.strip() or f"swappiness {value}")
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
