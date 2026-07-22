import logging
import shutil
import subprocess

from ..core_base import _CLOUD_SYNC_CONFIG, _SMB_CONFIG
from .config import load_json_config, save_json_config
from .process import _run_command

_logger = logging.getLogger(__name__)

def _rclone_available() -> bool:
    return shutil.which("rclone") is not None
 # _rclone_available

def _rclone_list_remotes() -> list[tuple[str, str]]:
    """Return [(name, type), …] for every configured rclone remote."""
    result = _run_command(["rclone", "listremotes", "--long"], timeout=5)
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
    return load_json_config(_CLOUD_SYNC_CONFIG, default={})
 # _load_sync_config

def _save_sync_config(cfg: dict) -> None:
    save_json_config(_CLOUD_SYNC_CONFIG, cfg)
 # _save_sync_config

def _load_smb_config() -> list[dict]:
    return load_json_config(_SMB_CONFIG, default=[])
 # _load_smb_config

def _save_smb_config(shares: list[dict]) -> None:
    save_json_config(_SMB_CONFIG, shares, mode=0o600)
 # _save_smb_config

def _systemd_escape_mount_path(path: str) -> str:
    """Return the systemd .mount unit filename for a given absolute mount path."""
    try:
        r = subprocess.run(
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
        r = subprocess.run(
            ["findmnt", "--noheadings", "--target", path],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False
 # _is_mounted
