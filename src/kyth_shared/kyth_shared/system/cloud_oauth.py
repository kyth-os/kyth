"""Cloud OAuth helper — Aurora rclone parity (N36)."""
from __future__ import annotations
from kyth_shared.commands import run

def rclone_oauth_command(remote: str = "onedrive") -> list[str]:
    return ["rclone", "config", "create", remote, "onedrive", "--all"]

def cloud_oauth_status() -> tuple[bool, str]:
    try:
        r = run(["rclone", "listremotes"], capture_output=True, text=True, timeout=5, check=False)
        if r.returncode == 0:
            rems = [l.strip() for l in r.stdout.splitlines() if l.strip()]
            return (True, f"rclone remotes: {', '.join(rems) or 'none'}")
        return (False, "rclone not configured — use Hub Cloud Storage OAuth")
    except FileNotFoundError:
        return (False, "rclone not installed")
    except (OSError, ValueError) as exc:
        return (False, str(exc))