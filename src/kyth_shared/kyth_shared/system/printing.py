"""Printing helper — Mint IPP parity (N34).

Uses ippfind + lpstat via commands.run, one-click system-config-printer --setup.
No new daemon, driver foomatic already baked.
"""
from __future__ import annotations

from kyth_shared.commands import run


def ipp_discover() -> list[str]:
    try:
        r = run(["ippfind"], capture_output=True, text=True, timeout=10, check=False)
        if r.returncode == 0 and r.stdout.strip():
            return [l.strip() for l in r.stdout.splitlines() if l.strip()][:20]
        r2 = run(["lpstat", "-e"], capture_output=True, text=True, timeout=5, check=False)
        if r2.returncode == 0 and r2.stdout.strip():
            return [l.strip() for l in r2.stdout.splitlines() if l.strip()][:20]
        return []
    except FileNotFoundError:
        return []
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        return []


def printer_setup_command() -> list[str]:
    return ["system-config-printer", "--setup"]
