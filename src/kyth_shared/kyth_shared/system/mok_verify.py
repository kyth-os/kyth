"""MOK verify helper — Nobara parity (N40)."""
from __future__ import annotations
from kyth_shared.commands import run

def mok_status() -> tuple[str, str]:
    try:
        r = run(["mokutil", "--sb-state"], capture_output=True, text=True, timeout=5, check=False)
        sb = r.stdout.lower() if r.returncode == 0 else ""
        sb_state = "enabled" if "secureboot enabled" in sb else "disabled" if "disabled" in sb else "unknown"
        r2 = run(["mokutil", "--list-enrolled"], capture_output=True, text=True, timeout=5, check=False)
        enrolled = "KythOS Secure Boot" in r2.stdout if r2.returncode == 0 else False
        return sb_state, "enrolled" if enrolled else "not enrolled"
    except FileNotFoundError:
        return "unknown", "mokutil not installed"
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
        return "unknown", str(exc)
