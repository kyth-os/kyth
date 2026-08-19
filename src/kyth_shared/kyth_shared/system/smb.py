"""SMB browser helper — Aurora autodiscover parity (N33).

Uses smbclient -L / avahi-browse via DataWorker + gio mount smb:// one-click,
no auto-mount on boot. Reuses NetworkManager-wait-online already enabled.
"""
from __future__ import annotations

from kyth_shared.commands import run


def smb_discover_command(host: str | None = None) -> list[str]:
    if host:
        return ["smbclient", "-L", host, "-N"]
    return ["avahi-browse", "-r", "_smb._tcp"]


def smb_mount_command(share: str) -> list[str]:
    # gio mount smb://host/share — user session, no sudo
    return ["gio", "mount", share]


def smb_browse_dry_run(host: str | None = None) -> tuple[bool, str]:
    cmd = smb_discover_command(host)
    try:
        r = run(cmd, capture_output=True, text=True, timeout=10, check=False)
        if r.returncode == 0:
            return True, r.stdout[:500]
        return False, r.stderr[:500] or f"{' '.join(cmd)} failed"
    except FileNotFoundError:
        return False, f"{cmd[0]} not installed"
    except Exception as exc:
        return False, str(exc)
