"""Cloud sync helpers (rclone / rsync command builders).

Pure stdlib — no Qt. Workers live in ``services.workers.cloud_sync``.
"""
from __future__ import annotations

import re


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


def rclone_config_create_command(
    name: str,
    service: str,
    token: str,
    *,
    extra_params: list[str] | None = None,
) -> list[str]:
    """Build ``rclone config create`` for OAuth remotes (drive/onedrive)."""
    cmd = [
        "rclone", "config", "create", name, service,
        "token", token,
    ]
    if extra_params:
        cmd.extend(extra_params)
    cmd.append("--non-interactive")
    return cmd


def rclone_create_remote(
    name: str,
    service: str,
    token: str,
    *,
    extra_params: list[str] | None = None,
    timeout: int = 30,
) -> tuple[bool, str]:
    """Create an rclone remote. Returns (ok, error_or_empty)."""
    from .process import run_command

    result = run_command(
        rclone_config_create_command(name, service, token, extra_params=extra_params),
        timeout=timeout,
    )
    if result is None:
        return False, "rclone is not installed or not on PATH."
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        return False, err[:300] or f"rclone config create failed ({result.returncode})"
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
