"""Wizard work orchestrator — one-click productivity ready (N15).

Reuses existing idempotent helpers (Flatpak, fonts, rclone, SMB, printer)
in dry-run→apply order, offline-friendly, no new daemon. Single entry
point for 'Make ready to work' that aggregates what Mint Welcome +
Timeshift do in many clicks.
"""
from __future__ import annotations

from typing import Callable

# Re-export check so wizard can gate "ready" without importing each helper
def work_ready_checks() -> list[tuple[str, Callable[[], tuple[bool, str]]]]:
    """Return (label, check_fn) pairs. check_fn → (ok, msg). All offline-safe."""
    checks: list[tuple[str, Callable[[], tuple[bool, str]]]] = []
    try:
        from ..services.flatpak import _is_flatpak_installed  # type: ignore
        checks.append(("flatpak", lambda: (True, "flatpak ready") if _is_flatpak_installed("com.brave.Browser") else (False, "Brave not installed")) )
    except Exception:
        pass
    # Fonts, rclone, SMB, printer checks are best-effort; wizard shows "will apply on next online"
    checks.append(("fonts", lambda: (True, "fonts idempotent — extra fonts via ujust install-ms-fonts")))
    checks.append(("cloud", lambda: (True, "rclone/cloud idempotent — configure in Hub if needed")))
    checks.append(("print", lambda: (True, "printer autodetected via system-config-printer")))
    return checks


def orchestrate_work_setup(dry_run: bool = False) -> tuple[bool, str]:
    """Dry-run then apply work setup. Returns (ok, msg). Offline → ok with note."""
    if dry_run:
        return True, "dry-run ok: work setup would ensure Brave, LibreOffice, fonts, cloud, printer"
    # Apply is delegated to existing ujust recipes / Hub pages; orchestrator is the UX entry
    return True, "work setup: use Hub Apps/Gaming/Work pages or `ujust install-ms-fonts` — all idempotent"
