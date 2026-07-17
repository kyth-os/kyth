import json
import os
import shlex
import shutil
import subprocess

from .config import load_json_config, save_json_config
from .process import _command_stdout, _run_command

_CLOUD_SYNC_CONFIG = os.path.expanduser("~/.config/kyth-cloud-sync.json")
_SMB_CONFIG = os.path.expanduser("~/.config/kyth-smb-shares.json")
_SMB_CREDS_DIR = "/etc/kyth-smb-creds"

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
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
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
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False
 # _is_mounted

def _build_add_share_script(share: dict, mount_now: bool) -> str:
    import base64 as _b64
    name       = share["name"]
    server     = share["server"]
    share_path = share["share_path"].lstrip("/")
    mount_pt   = share["mount_point"]
    username   = share["username"]
    password   = share.get("password", "")
    domain     = share.get("domain", "")
    auto_mount = share.get("auto_mount", False)
    uid        = os.getuid()
    gid        = os.getgid()

    unit_name  = _systemd_escape_mount_path(mount_pt)
    cred_file  = f"{_SMB_CREDS_DIR}/{name}"
    unc        = f"//{server}/{share_path}"
    opts       = (
        f"credentials={cred_file},uid={uid},gid={gid},"
        "iocharset=utf8,vers=3.0,nofail,_netdev"
    )

    creds = f"username={username}\npassword={password}\n"
    if domain:
        creds += f"domain={domain}\n"
    creds_b64 = _b64.b64encode(creds.encode()).decode()

    unit = "\n".join([
        "[Unit]",
        f"Description=SMB Share {unc}",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Mount]",
        f"What={unc}",
        f"Where={mount_pt}",
        "Type=cifs",
        f"Options={opts}",
        "TimeoutSec=30",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
    ])
    unit_b64 = _b64.b64encode(unit.encode()).decode()
    creds_dir_q = shlex.quote(_SMB_CREDS_DIR)
    cred_file_q = shlex.quote(cred_file)
    mount_pt_q = shlex.quote(mount_pt)
    unit_path_q = shlex.quote(f"/etc/systemd/system/{unit_name}")
    unit_name_q = shlex.quote(unit_name)

    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"mkdir -p {creds_dir_q}",
        f"chmod 700 {creds_dir_q}",
        f"echo '{creds_b64}' | base64 -d > {cred_file_q}",
        f"chmod 600 {cred_file_q}",
        f"mkdir -p {mount_pt_q}",
        f"echo '{unit_b64}' | base64 -d > {unit_path_q}",
        "systemctl daemon-reload",
    ]
    if auto_mount:
        lines.append(f"systemctl enable {unit_name_q}")
    if mount_now:
        lines.append(f"systemctl start {unit_name_q} || true")

    return "\n".join(lines)
 # _build_add_share_script

def _build_remove_share_script(share: dict) -> str:
    name      = share["name"]
    mount_pt  = share["mount_point"]
    unit_name = _systemd_escape_mount_path(mount_pt)
    cred_file = f"{_SMB_CREDS_DIR}/{name}"
    unit_name_q = shlex.quote(unit_name)
    unit_path_q = shlex.quote(f"/etc/systemd/system/{unit_name}")
    cred_file_q = shlex.quote(cred_file)

    return "\n".join([
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"systemctl stop {unit_name_q} 2>/dev/null || true",
        f"systemctl disable {unit_name_q} 2>/dev/null || true",
        f"rm -f {unit_path_q}",
        "systemctl daemon-reload",
        f"rm -f {cred_file_q}",
    ])
 # _build_remove_share_script
