"""Unified update helper — bootc + flatpak + firmware + rollback (N37).

Single Hub card beats Nobara scattered dnf/flatpak/fwupd. Uses firmware.py
single-source, flatpak via flatpak subcommand, bootc via bootc. Rollback is
bootc rollback Worker with ostree admin status 2 deploys intact.
"""
from __future__ import annotations

from kyth_shared.commands import run


def pending_updates_summary() -> dict[str, str]:
    out: dict[str, str] = {}
    # firmware via single source
    try:
        from kyth_shared.system.firmware import check_firmware_updates
        out["firmware"] = str(check_firmware_updates())
    except Exception:
        out["firmware"] = "0"
    # flatpak
    try:
        r = run(["flatpak", "remote-ls", "--updates"], capture_output=True, text=True, timeout=15, check=False)
        if r.returncode == 0:
            lines = [l for l in r.stdout.splitlines() if l.strip()]
            out["flatpak"] = str(len(lines))
        else:
            out["flatpak"] = "0"
    except Exception:
        out["flatpak"] = "0"
    # bootc
    try:
        r = run(["bootc", "status", "--json"], capture_output=True, text=True, timeout=10, check=False)
        out["bootc"] = "staged" if "staged" in r.stdout.lower() else "current"
    except Exception:
        out["bootc"] = "unknown"
    return out


def rollback_command() -> list[str]:
    return ["bootc", "rollback"]
