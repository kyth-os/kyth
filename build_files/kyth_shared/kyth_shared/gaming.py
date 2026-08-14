"""Shared gaming session & process detection utilities.

Used by kyth-sched and kyth-update-watcher to avoid duplicate busctl/proc scanning code.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from kyth_shared.commands import run_text

_GAMING_CACHE: dict[tuple, tuple[float, str | None]] = {}
_GAMING_TTL = 30.0


def invalidate_gaming_cache() -> None:
    """Clear gaming detection cache (for tests)."""
    _GAMING_CACHE.clear()

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
    Results are cached 30s to avoid thundering herd on busctl/proc scans.
    """ 
    _key = (uid, check_all_uids)
    _now = time.monotonic()
    if _key in _GAMING_CACHE:
        _ts, _val = _GAMING_CACHE[_key]
        if _now - _ts < _GAMING_TTL:
            return _val
    uids = _active_uids() if check_all_uids else []
    if uid is not None and uid not in uids:
        uids.append(uid)
    if not uids:
        uids = [os.getuid()]

    # 1. Gamescope check
    for u in uids:
        if gamescope_session_active(u):
            _res = f"gamescope session active (uid {u})"
            _GAMING_CACHE[_key] = (_now, _res)
            return _res

    # 2. GameMode D-Bus check
    for u in uids:
        if gamemode_active(u):
            _res = f"GameMode active (uid {u})"
            _GAMING_CACHE[_key] = (_now, _res)
            return _res

    # 3. Proc scan check
    if proc_gaming_active():
        _res: str | None = "gaming process detected (/proc scan)"
        _GAMING_CACHE[_key] = (_now, _res)
        return _res

    _GAMING_CACHE[_key] = (_now, None)
    return None


def find_controllers() -> list[str]:
    """Scan /dev/input using udevadm for connected gamepads and joysticks."""
    import re
    from kyth_shared.commands import run as run_command
    controllers = []
    dev_input = Path("/dev/input")
    if not dev_input.is_dir():
        return controllers

    for path in sorted(dev_input.glob("event*")):
        res = run_command(
            ["udevadm", "info", "--query=property", "--name", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            continue
        props = res.stdout

        name = None
        for prop in ("ID_MODEL_FROM_DATABASE", "ID_MODEL", "NAME"):
            m = re.search(rf"^{prop}=(.*)$", props, re.MULTILINE)
            if m:
                name = m.group(1).strip()
                if name.startswith('"') and name.endswith('"'):
                    name = name[1:-1]
                break

        check_str = f"{name or ''} {props}".lower()
        keywords = ("joystick", "gamepad", "xbox", "dualsense", "dualshock", "playstation", "controller")
        if any(kw in check_str for kw in keywords):
            controllers.append(f"{path} {name or 'controller'}")

    return controllers


