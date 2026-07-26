"""Shared gaming session & process detection utilities.

Used by kyth-sched and kyth-update-watcher to avoid duplicate busctl/proc scanning code.
"""
from __future__ import annotations

import os
from pathlib import Path

from kyth_shared.commands import run_text

# Process names that indicate a game is active
GAMING_PROCS = frozenset(
    {
        "gamescope",
        "wine",
        "wine64",
        "wineserver",
        "wine-preloader",
        "pressure-vessel-wrap",
    }
)


def _active_uids() -> list[int]:
    """Return UIDs with active systemd user sessions."""
    result = run_text(
        ["loginctl", "list-sessions", "--no-legend", "--no-pager"],
        timeout=5,
    )
    if result is None:
        return []
    uids: list[int] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            try:
                uids.append(int(parts[2]))
            except ValueError:
                pass
    return list(set(uids))


def gamescope_session_active(uid: int) -> bool:
    """Check if gamescope session lock file exists for a user."""
    return Path(f"/run/user/{uid}/gamescope-session.lock").exists()


def gamemode_active(uid: int) -> bool:
    """Query GameMode status over D-Bus for a user."""
    env = {
        **os.environ,
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{uid}/bus",
    }
    result = run_text(
        [
            "busctl",
            "--user",
            "--address",
            f"unix:path=/run/user/{uid}/bus",
            "call",
            "com.feralinteractive.GameMode",
            "/com/feralinteractive/GameMode",
            "com.feralinteractive.GameMode",
            "QueryStatus",
            "i",
            "0",
        ],
        timeout=3,
        env=env,
    )
    if result is not None and result.returncode == 0 and result.stdout.strip():
        try:
            val = result.stdout.strip().split()[-1]
            return int(val) > 0
        except (IndexError, ValueError):
            return False
    return False


def proc_gaming_active() -> bool:
    """Scan /proc for running processes matching known gaming executables."""
    try:
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue
            try:
                exe = os.readlink(f"/proc/{entry.name}/exe")
                if Path(exe).name.lower() in GAMING_PROCS:
                    return True
            except OSError:
                pass
    except OSError:
        pass
    return False


def check_gaming_reason(
    *, uid: int | None = None, check_all_uids: bool = False
) -> str | None:
    """Check if gaming is active and return a description of the trigger, or None.

    If check_all_uids is True, all active loginctl sessions are scanned.
    """
    uids = _active_uids() if check_all_uids else []
    if uid is not None and uid not in uids:
        uids.append(uid)
    if not uids:
        uids = [os.getuid()]

    # 1. Gamescope check
    for u in uids:
        if gamescope_session_active(u):
            return f"gamescope session active (uid {u})"

    # 2. GameMode D-Bus check
    for u in uids:
        if gamemode_active(u):
            return f"GameMode active (uid {u})"

    # 3. Proc scan check
    if proc_gaming_active():
        return "gaming process detected (/proc scan)"

    return None
