"""Shared atomic file write helpers — tmp+fsync+replace.

Consolidates the 9 copy-pasted _atomic_write_text implementations previously
spread across gpu_power, flatpak_prefetch, flatpak_trim, guardian,
vm_acceptance, explorer_preset, hardware_policy, fcitx_latency,
quicksettings, plasma_drift, etc.

All writers use mkstemp in the target's parent directory, fsync the
temporary file, atomically replace, then fsync the parent directory so a
power loss leaves either the old file or the new file — never a torn
write.  Symlink targets are refused to avoid TOCTOU overwrite when running
as root.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(
    path: Path | str,
    content: str,
    encoding: str = "utf-8",
    mode: int | None = None,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Refuse to overwrite a symlink at the target before creating tmp
    if path.is_symlink():
        raise OSError(f"refusing to replace symlink: {path}")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        if mode is not None:
            try:
                os.fchmod(fd, mode)
            except OSError:
                pass
        # Double-check tmp itself is not a symlink
        try:
            if tmp_path.is_symlink():
                raise OSError(f"refusing to write through symlink tmp: {tmp_path}")
        except OSError:
            raise
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        fd = -1  # fd now owned/closed by fdopen
        if path.is_symlink():
            raise OSError(f"refusing to replace symlink: {path}")
        os.replace(tmp_name, path)
        try:
            dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except BaseException:
        # Close fd if fdopen didn't take ownership
        if fd != -1:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            tmp_path.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
        raise


def atomic_write_bytes(
    path: Path | str,
    data: bytes,
    mode: int | None = None,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OSError(f"refusing to replace symlink: {path}")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        if mode is not None:
            try:
                os.fchmod(fd, mode)
            except OSError:
                pass
        if tmp_path.is_symlink():
            raise OSError(f"refusing to write through symlink tmp: {tmp_path}")
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        fd = -1
        if path.is_symlink():
            raise OSError(f"refusing to replace symlink: {path}")
        os.replace(tmp_name, path)
        try:
            dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except BaseException:
        if fd != -1:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            tmp_path.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
        raise


def atomic_write_json(
    path: Path | str,
    payload: Any,
    mode: int | None = 0o600,
) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    atomic_write_text(path, text, encoding="utf-8", mode=mode)


__all__ = ["atomic_write_text", "atomic_write_bytes", "atomic_write_json"]
