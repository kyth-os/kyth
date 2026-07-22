"""Root-side implementation for System Hub SMB share mutations."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


CREDS_DIR = Path("/etc/kyth/smb-credentials")
UNIT_DIR = Path("/etc/systemd/system")
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SAFE_HOST_RE = re.compile(r"^[A-Za-z0-9._:-]{1,253}$")
_SAFE_MOUNT_PATH_RE = re.compile(r"^[A-Za-z0-9._/ -]+$")
_SAFE_UNIT_RE = re.compile(r"^[A-Za-z0-9_.@\\-]+\.mount$")
_SAFE_MOUNT_PREFIXES = ("/mnt/", "/media/", "/run/media/", "/home/")
_MAX_PAYLOAD = 64 * 1024


def _plain(value: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    if not allow_empty and not value:
        raise ValueError(f"{field} is required")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{field} contains control characters")
    return value


def _mount_point(value: object) -> str:
    path = os.path.normpath(_plain(value, "mount_point"))
    if not _SAFE_MOUNT_PATH_RE.fullmatch(path):
        raise ValueError("mount_point contains unsupported characters")
    if not any(path.startswith(prefix) for prefix in _SAFE_MOUNT_PREFIXES):
        raise ValueError("mount_point is outside an approved prefix")
    return path


def _unit_name(mount_point: str) -> str:
    result = subprocess.run(
        ["systemd-escape", "--path", "--suffix=mount", mount_point],
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )
    unit = result.stdout.strip()
    if not _SAFE_UNIT_RE.fullmatch(unit):
        raise ValueError("systemd-escape returned an invalid mount unit")
    return unit


def _ensure_mount_path_safe(mount_point: str) -> None:
    """Reject symlinks in an existing mount path before creating directories."""
    current = Path(mount_point)
    while True:
        if current.exists() and current.is_symlink():
            raise ValueError(f"mount_point traverses a symlink: {current}")
        parent = current.parent
        if parent == current:
            return
        current = parent


def _payload(stream=None) -> dict:
    raw = (stream or sys.stdin.buffer).read(_MAX_PAYLOAD + 1)
    if len(raw) > _MAX_PAYLOAD:
        raise ValueError("share payload is too large")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("share payload must be an object")
    return value


def _atomic_write(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError(f"refusing to replace symlink: {path}")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def add_share(share: dict) -> None:
    name = _plain(share.get("name"), "name")
    if not _SAFE_NAME_RE.fullmatch(name):
        raise ValueError("name contains unsupported characters")
    server = _plain(share.get("server"), "server")
    if not _SAFE_HOST_RE.fullmatch(server):
        raise ValueError("server is not a hostname or IP address")
    share_path = _plain(share.get("share_path"), "share_path").lstrip("/")
    if not share_path or share_path.startswith(".") or "//" in share_path or "%" in share_path:
        raise ValueError("share_path is invalid")
    username = _plain(share.get("username"), "username")
    password = _plain(share.get("password", ""), "password", allow_empty=True)
    domain = _plain(share.get("domain", ""), "domain", allow_empty=True)
    mount_point = _mount_point(share.get("mount_point"))
    auto_mount = share.get("auto_mount") is True
    mount_now = share.get("mount_now") is True
    uid = share.get("uid")
    gid = share.get("gid")
    if not isinstance(uid, int) or not isinstance(gid, int) or uid < 0 or gid < 0:
        raise ValueError("uid and gid must be non-negative integers")

    unit = _unit_name(mount_point)
    credential_path = CREDS_DIR / name
    unit_path = UNIT_DIR / unit
    credentials = f"username={username}\npassword={password}\n"
    if domain:
        credentials += f"domain={domain}\n"
    unc = f"//{server}/{share_path}"
    options = (
        f"credentials={credential_path},uid={uid},gid={gid},"
        "iocharset=utf8,vers=3.0,nofail,_netdev"
    )
    unit_text = "\n".join((
        "[Unit]",
        f"Description=KythOS SMB Share {name}",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Mount]",
        f"What={unc}",
        f"Where={mount_point}",
        "Type=cifs",
        f"Options={options}",
        "TimeoutSec=30",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "",
    ))

    _ensure_mount_path_safe(mount_point)
    Path(mount_point).mkdir(parents=True, exist_ok=True)
    _atomic_write(credential_path, credentials, 0o600)
    _atomic_write(unit_path, unit_text, 0o644)
    subprocess.run(["systemctl", "daemon-reload"], check=True, timeout=30)
    if auto_mount:
        subprocess.run(["systemctl", "enable", unit], check=True, timeout=30)
    else:
        subprocess.run(["systemctl", "disable", unit], check=False, timeout=30)
    if mount_now:
        subprocess.run(["systemctl", "start", unit], check=True, timeout=45)


def remove_share(share: dict) -> None:
    name = _plain(share.get("name"), "name")
    if not _SAFE_NAME_RE.fullmatch(name):
        raise ValueError("name contains unsupported characters")
    mount_point = _mount_point(share.get("mount_point"))
    unit = _unit_name(mount_point)
    subprocess.run(["systemctl", "stop", unit], check=False, timeout=30)
    subprocess.run(["systemctl", "disable", unit], check=False, timeout=30)
    unit_path = UNIT_DIR / unit
    credential_path = CREDS_DIR / name
    if unit_path.is_symlink() or credential_path.is_symlink():
        raise ValueError("refusing to remove a symlinked share artifact")
    unit_path.unlink(missing_ok=True)
    credential_path.unlink(missing_ok=True)
    subprocess.run(["systemctl", "daemon-reload"], check=True, timeout=30)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if os.geteuid() != 0:
        print("kyth-network-share must run as root", file=sys.stderr)
        return 77
    if len(args) != 1 or args[0] not in {"add", "remove"}:
        print("Usage: kyth-network-share {add|remove}", file=sys.stderr)
        return 64
    try:
        share = _payload()
        add_share(share) if args[0] == "add" else remove_share(share)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(f"Network share {args[0]} failed: {exc}", file=sys.stderr)
        return 1
    return 0
