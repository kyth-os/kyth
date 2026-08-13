"""Cloud sync helpers (rclone / rsync command builders).

Pure stdlib — no Qt. Workers live in ``services.workers.cloud_sync``.
"""
from __future__ import annotations

import configparser
import fcntl
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path


_REMOTE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. -]{0,63}$")
_CONFIG_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def extract_rclone_token(text: str) -> str | None:
    """Parse token JSON from `rclone authorize` stdout/stderr."""
    start_marker = "Paste the following into your remote machine --->"
    end_marker = "<---End paste"
    if start_marker in text and end_marker in text:
        start = text.index(start_marker) + len(start_marker)
        end = text.index(end_marker, start)
        candidate = text[start:end].strip()
        if candidate.startswith("{"):
            return candidate
    m = re.search(r'\{"access_token"[^<>]*\}', text, re.DOTALL)
    if m:
        return m.group(0)
    return None


_extract_rclone_token = extract_rclone_token


def rclone_sync_command(remote: str, folder: str) -> list[str]:
    return [
        "rclone", "sync", f"{remote}:", folder,
        "--progress", "--stats-one-line", "--stats=2s",
    ]


def rsync_copy_command(src: str, dst: str) -> list[str]:
    return [
        "rsync", "-a", "--info=name1,progress2", "--no-inc-recursive",
        src.rstrip("/") + "/",
        dst.rstrip("/") + "/",
    ]


def _rclone_config_path() -> Path:
    override = os.environ.get("RCLONE_CONFIG")
    if override:
        return Path(os.path.abspath(os.path.expanduser(override)))
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return Path(os.path.abspath(base / "rclone" / "rclone.conf"))


def _rclone_remote_values(
    service: str,
    token: str,
    extra_params: list[str] | None,
) -> dict[str, str]:
    if service not in {"drive", "onedrive"}:
        raise ValueError("Unsupported rclone OAuth service")
    try:
        token_data = json.loads(token)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("rclone returned an invalid OAuth token") from exc
    if not isinstance(token_data, dict) or not isinstance(token_data.get("access_token"), str):
        raise ValueError("rclone OAuth token has no access_token")
    values = {
        "type": service,
        "token": json.dumps(token_data, separators=(",", ":")),
    }
    params = extra_params or []
    if len(params) % 2:
        raise ValueError("rclone configuration options must be key/value pairs")
    for key, value in zip(params[::2], params[1::2]):
        if not _CONFIG_KEY_RE.fullmatch(key) or any(char in value for char in "\0\r\n"):
            raise ValueError("rclone configuration contains an invalid option")
        values[key] = value
    return values


def _write_rclone_remote(name: str, values: dict[str, str], config_path: Path) -> None:
    """Atomically update a plaintext, user-owned rclone configuration."""
    if not _REMOTE_NAME_RE.fullmatch(name):
        raise ValueError("Invalid rclone remote name")
    config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    config_path.parent.chmod(0o700)
    lock_path = config_path.with_name(f".{config_path.name}.lock")
    flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    lock_fd = os.open(lock_path, flags, 0o600)
    try:
        os.fchmod(lock_fd, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        parser = configparser.RawConfigParser(interpolation=None)
        parser.optionxform = str
        if config_path.exists() or config_path.is_symlink():
            info = config_path.lstat()
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid():
                raise ValueError("rclone config is not a regular user-owned file")
            existing = config_path.read_text(encoding="utf-8")
            if existing.lstrip().startswith("RCLONE_ENCRYPT_V"):
                raise ValueError("Encrypted rclone configs must be edited with `rclone config`")
            parser.read_string(existing)
        if parser.has_section(name):
            parser.remove_section(name)
        parser.add_section(name)
        for key, value in values.items():
            parser.set(name, key, value)

        temp_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=config_path.parent,
                prefix=f".{config_path.name}.", delete=False,
            ) as handle:
                temp_name = handle.name
                os.fchmod(handle.fileno(), 0o600)
                parser.write(handle, space_around_delimiters=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, config_path)
            temp_name = ""
        finally:
            if temp_name:
                Path(temp_name).unlink(missing_ok=True)
    finally:
        os.close(lock_fd)


def rclone_create_remote(
    name: str,
    service: str,
    token: str,
    *,
    extra_params: list[str] | None = None,
    timeout: int = 30,
) -> tuple[bool, str]:
    """Create an rclone remote without placing its OAuth token in argv."""
    del timeout  # Retained for API compatibility with the former CLI call.
    if not shutil.which("rclone"):
        return False, "rclone is not installed or not on PATH."
    try:
        values = _rclone_remote_values(service, token, extra_params)
        _write_rclone_remote(name, values, _rclone_config_path())
    except (OSError, ValueError, configparser.Error) as exc:
        return False, str(exc)[:300]
    return True, ""


def rclone_verify_remote(name: str, *, timeout: int = 20) -> tuple[bool, str]:
    """List remote root; returns (ok, error_hint)."""
    from .process import run_command

    result = run_command(
        ["rclone", "lsd", f"{name}:", "--max-depth", "0"],
        timeout=timeout,
    )
    if result is None:
        return False, "rclone is not installed or not on PATH."
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "").strip()[:200]
    return True, ""


def rclone_usage_hints(name: str, folder: str) -> str:
    return (
        f"# Sync cloud → local (one-shot):\n"
        f"rclone sync {name}: {folder} --progress\n\n"
        f"# Mount as a virtual drive (stays open until unmounted):\n"
        f"rclone mount {name}: {folder} --daemon --vfs-cache-mode full"
    )


def __getattr__(name: str):
    if name in {"SteamCopyWorker", "RcloneAuthorizeWorker", "RcloneSyncWorker"}:
        from .workers import cloud_sync as m
        return getattr(m, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
