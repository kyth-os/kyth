import logging
import os
import re
import shutil
from kyth_welcome.services.command import run_sync
from dataclasses import dataclass

from ..core_base import CLOUD_SYNC_CONFIG, SMB_CONFIG
from .config import load_json_config, save_json_config
from .network_share_helper import _mount_point
from .process import run_command

_logger = logging.getLogger(__name__)

def _rclone_available() -> bool:
    return shutil.which("rclone") is not None
 # _rclone_available

def _rclone_list_remotes() -> list[tuple[str, str]]:
    """Return [(name, type), …] for every configured rclone remote."""
    result = run_command(["rclone", "listremotes", "--long"], timeout=5)
    if result is None or result.returncode != 0:
        return []
    remotes: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            remotes.append((parts[0].rstrip(":"), parts[1].lower()))
    return remotes
 # _rclone_list_remotes

def _rclone_has_remote_type(remote_type: str) -> bool:
    """Return True only when a remote whose type is *exactly* remote_type exists."""
    return any(rtype == remote_type.lower() for _, rtype in _rclone_list_remotes())
 # _rclone_has_remote_type

def _load_sync_config() -> dict:
    """Load {remote_name: {folder, last_sync, last_ok}} from disk."""
    return load_json_config(CLOUD_SYNC_CONFIG, default={})
 # _load_sync_config

def _save_sync_config(cfg: dict) -> None:
    save_json_config(CLOUD_SYNC_CONFIG, cfg)
 # _save_sync_config

def _load_smb_config() -> list[dict]:
    return load_json_config(SMB_CONFIG, default=[])
 # _load_smb_config

def _save_smb_config(shares: list[dict]) -> None:
    save_json_config(SMB_CONFIG, shares, mode=0o600)
 # _save_smb_config

def _systemd_escape_mount_path(path: str) -> str:
    """Return the systemd .mount unit filename for a given absolute mount path."""
    try:
        r = run_sync(
            ["systemd-escape", "--path", "--suffix=mount", path],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        _logger.debug("_systemd_escape_mount_path: systemd-escape probe of %s failed", path, exc_info=True)
    # Fallback: strip leading /, replace / with -, append .mount
    return path.lstrip("/").replace("/", "-") + ".mount"
 # _systemd_escape_mount_path

def _is_cifs_available() -> bool:
    return bool(shutil.which("mount.cifs"))
 # _is_cifs_available

def _is_mounted(path: str) -> bool:
    try:
        r = run_sync(
            ["findmnt", "--noheadings", "--target", path],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False
 # _is_mounted


@dataclass(frozen=True)
class ShareFormResult:
    """Either `share` (validation passed) or both error fields are set —
    no Qt, so page_network_shares.py's add/reconnect form validation is
    testable without a display."""
    share: dict | None = None
    error_title: str = ""
    error_message: str = ""


def validate_share_form(
    *, name: str, server: str, share_path: str, mount_pt: str, username: str,
    password: str, domain: str, auto_mount: bool,
    existing_names: set[str], reconnect_name: str | None,
) -> ShareFormResult:
    """Validate already-stripped form field values. `mount_pt` may be empty
    (defaulted from `name`) but every other field is required."""
    if not name:
        return ShareFormResult(error_title="Missing Field", error_message="Please enter a Share Name.")
    if not server:
        return ShareFormResult(error_title="Missing Field", error_message="Please enter a Server address.")
    if not share_path:
        return ShareFormResult(error_title="Missing Field", error_message="Please enter the Share Path.")
    if not username:
        return ShareFormResult(error_title="Missing Field", error_message="Please enter a Username.")

    safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
    if not mount_pt:
        mount_pt = f"/mnt/kyth/{safe_name}"
    mount_pt = os.path.expanduser(mount_pt)
    # Same validation the root-side add/remove helper enforces (it runs as
    # root and creates this directory, so mounting over /etc or /usr would
    # corrupt the system) — checked here too so bad input gets a friendly
    # message immediately instead of a less-clear failure from the helper.
    try:
        mount_pt = _mount_point(mount_pt)
    except ValueError:
        return ShareFormResult(
            error_title="Invalid Mount Point",
            error_message=(
                "Mount point must be under /mnt/, /media/, /run/media/, or /home/, "
                "and contain only letters, numbers, spaces, '.', '_', '-', or '/'."
            ),
        )

    if safe_name in existing_names and safe_name != reconnect_name:
        return ShareFormResult(
            error_title="Duplicate Name",
            error_message=f'A share named "{safe_name}" already exists. Remove it first or use a different name.',
        )

    return ShareFormResult(share={
        "name":       safe_name,
        "server":     server,
        "share_path": share_path.lstrip("/"),
        "mount_point": mount_pt,
        "username":   username,
        "password":   password,
        "domain":     domain,
        "auto_mount": auto_mount,
    })
