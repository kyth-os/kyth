"""Small helpers for launching external apps from System Hub pages.

Centralizes ``subprocess.Popen`` patterns (flatpak, kcmshell, systemsettings)
so pages stay thin and idle-inhibit can be applied consistently later.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Sequence

from kyth_shared.commands import APPLICATION_RUNNER

from .privileged import PrivilegedAction, PrivilegedGateway

PRIVILEGED_GATEWAY = PrivilegedGateway()


def popen(cmd: Sequence[str], *, env: dict[str, str] | None = None) -> subprocess.Popen | None:
    """Fire-and-forget process start; returns None if the binary is missing."""
    if not cmd:
        return None
    binary = cmd[0]
    if binary in {"sudo", "pkexec"}:
        raise ValueError("privileged commands must use popen_privileged()")
    if binary not in ("flatpak", "bash", "env") and not os.path.isabs(binary):
        if shutil.which(binary) is None:
            return None
    try:
        return APPLICATION_RUNNER.spawn(
            list(cmd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
    except OSError:
        return None


def popen_privileged(action: PrivilegedAction) -> subprocess.Popen | None:
    """Launch a command that has passed the centralized privilege policy."""
    try:
        return PRIVILEGED_GATEWAY.spawn(
            action,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return None


def flatpak_run(app_id: str, *args: str) -> subprocess.Popen | None:
    return popen(["flatpak", "run", app_id, *args])


def kcmshell(module: str) -> subprocess.Popen | None:
    for binary in ("kcmshell6", "kcmshell5"):
        if shutil.which(binary):
            return popen([binary, module])
    return None


def systemsettings(*args: str) -> subprocess.Popen | None:
    for binary in ("systemsettings", "systemsettings5"):
        if shutil.which(binary):
            return popen([binary, *args])
    return None


def open_settings_module(module: str) -> subprocess.Popen | None:
    """Open a KCM via kcmshell, then systemsettings."""
    return kcmshell(module) or systemsettings(module) or systemsettings()


def reboot() -> subprocess.Popen | None:
    return popen(["systemctl", "reboot"])


def open_terminal_command(command: str) -> subprocess.Popen | None:
    """Run *command* in the first available terminal."""
    for terminal in ("konsole", "kgx", "gnome-terminal"):
        if not shutil.which(terminal):
            continue
        if terminal == "konsole":
            proc = popen([terminal, "-e", "bash", "-lc", command])
        else:
            proc = popen([terminal, "--", "bash", "-lc", command])
        if proc is not None:
            return proc
    return None


def open_first(*candidates: Sequence[str]) -> subprocess.Popen | None:
    """Try command lists in order; return the first that starts."""
    for cmd in candidates:
        proc = popen(cmd)
        if proc is not None:
            return proc
    return None
