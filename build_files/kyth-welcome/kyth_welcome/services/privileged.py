"""Validated construction of every privileged System Hub mutation.

UI pages describe an action; they do not assemble sudo, pkexec, bootc, or
systemctl command lines themselves. Keep this module free of Qt so its policy
is cheap to test and usable by non-UI callers.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable, Mapping


class PrivilegedActionError(ValueError):
    """Raised before authentication when an action is outside policy."""


class AuthFrontend(StrEnum):
    SUDO_ASKPASS = "sudo-askpass"
    PKEXEC = "pkexec"


@dataclass(frozen=True)
class PrivilegedAction:
    name: str
    argv: tuple[str, ...]
    timeout: float = 300
    sensitive_options: tuple[str, ...] = ()

    def command(self) -> list[str]:
        return list(self.argv)

    def display_command(self) -> list[str]:
        command = self.command()
        for index, value in enumerate(command[:-1]):
            if value in self.sensitive_options:
                command[index + 1] = "<redacted>"
        return command


_SAFE_ENV_KEYS = frozenset({
    "DBUS_SESSION_BUS_ADDRESS",
    "DESKTOP_STARTUP_ID",
    "DISPLAY",
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "SUDO_ASKPASS",
    "WAYLAND_DISPLAY",
    "XAUTHORITY",
    "XDG_CURRENT_DESKTOP",
    "XDG_RUNTIME_DIR",
})


def sanitized_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Keep desktop/auth context while dropping loader and interpreter injection."""
    environment = source if source is not None else os.environ
    return {key: value for key, value in environment.items() if key in _SAFE_ENV_KEYS}


class PrivilegedGateway:
    """The sole execution boundary for validated privileged actions."""

    def __init__(
        self,
        *,
        run: Callable[..., Any] = subprocess.run,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
        audit: Callable[[str], None] | None = None,
    ) -> None:
        self._run = run
        self._popen = popen
        self._audit = audit or (lambda _message: None)

    def run(self, action: PrivilegedAction, **kwargs: Any):
        kwargs.setdefault("check", False)
        kwargs.setdefault("timeout", action.timeout)
        kwargs.setdefault("env", sanitized_environment())
        kwargs["shell"] = False
        self._audit(f"privileged action {action.name}: {' '.join(action.display_command())}")
        return self._run(action.command(), **kwargs)

    def spawn(self, action: PrivilegedAction, **kwargs: Any) -> subprocess.Popen:
        kwargs.setdefault("env", sanitized_environment())
        kwargs["shell"] = False
        self._audit(f"privileged action {action.name}: {' '.join(action.display_command())}")
        return self._popen(action.command(), **kwargs)


_SAFE_IMAGE_REF_RE = re.compile(r"^[A-Za-z0-9._/@:+-]+$")
_SAFE_GATEWAY_RE = re.compile(r"^[A-Za-z0-9._:/?&=%+@\[\]-]+$")
_SAFE_SCHEDULER_RE = re.compile(r"^scx_[A-Za-z0-9_-]+$")
_SAFE_SYSTEMD_UNIT_RE = re.compile(r"^[A-Za-z0-9_.@\\-]+\.(?:service|timer|mount)$")
_SYSTEMCTL_ACTIONS = frozenset({"start", "stop", "restart", "enable", "disable"})
_SYSTEM_UNITS = frozenset({
    "bluetooth.service",
    "cups.service",
    "kyth-default-flatpaks.service",
    "kyth-update-watcher.service",
    "kyth-update-watcher.timer",
})
_HELPERS: dict[str, str] = {
    "network-share": "/usr/libexec/kyth-network-share",
    "hardware-setup": "/usr/libexec/kyth-retry-hardware-setup",
    "rclone-update": "/usr/bin/kyth-rclone-update",
    "sleep-mode": "/usr/libexec/kyth-set-sleep-mode",
    "xone-dongle-install": "/usr/bin/xone-dongle-install",
    "xone-firmware-install": "/usr/bin/xone-firmware-install",
}


def _prefix(frontend: AuthFrontend) -> tuple[str, ...]:
    if frontend is AuthFrontend.SUDO_ASKPASS:
        return ("sudo", "-A")
    if frontend is AuthFrontend.PKEXEC:
        return ("pkexec",)
    raise PrivilegedActionError(f"Unsupported authentication frontend: {frontend}")


def bootc_action(action: str, image_ref: str | None = None) -> PrivilegedAction:
    if action not in {"upgrade", "rollback", "reset", "switch"}:
        raise PrivilegedActionError(f"Unsupported bootc action: {action}")
    args = ["bootc", action]
    if action == "switch":
        if not image_ref or not _SAFE_IMAGE_REF_RE.fullmatch(image_ref):
            raise PrivilegedActionError("bootc switch requires a safe image reference")
        args.append(image_ref)
    elif image_ref is not None:
        raise PrivilegedActionError(f"bootc {action} does not accept an image reference")
    return PrivilegedAction(
        name=f"bootc-{action}",
        argv=(*_prefix(AuthFrontend.SUDO_ASKPASS), *args),
    )


def systemctl_action(
    action: str,
    unit: str,
    *,
    now: bool = False,
    frontend: AuthFrontend = AuthFrontend.SUDO_ASKPASS,
) -> PrivilegedAction:
    if action not in _SYSTEMCTL_ACTIONS:
        raise PrivilegedActionError(f"Unsupported systemctl action: {action}")
    if not _SAFE_SYSTEMD_UNIT_RE.fullmatch(unit):
        raise PrivilegedActionError(f"Invalid systemd unit name: {unit}")
    if unit not in _SYSTEM_UNITS and not unit.endswith(".mount"):
        raise PrivilegedActionError(f"System Hub may not mutate unit: {unit}")
    if now and action not in {"enable", "disable"}:
        raise PrivilegedActionError("--now is only valid for enable/disable actions")
    args = ["systemctl", action]
    if now:
        args.append("--now")
    args.append(unit)
    return PrivilegedAction(
        name=f"systemctl-{action}",
        argv=(*_prefix(frontend), *args),
    )


def helper_action(
    helper: str,
    *args: str,
    frontend: AuthFrontend = AuthFrontend.SUDO_ASKPASS,
) -> PrivilegedAction:
    executable = _HELPERS.get(helper)
    if executable is None:
        raise PrivilegedActionError(f"Unsupported privileged helper: {helper}")
    if any(not arg or "\0" in arg or "\n" in arg or "\r" in arg for arg in args):
        raise PrivilegedActionError("Privileged helper arguments contain invalid data")
    if helper == "network-share" and (len(args) != 1 or args[0] not in {"add", "remove"}):
        raise PrivilegedActionError("network-share accepts only add or remove")
    if helper == "rclone-update" and args:
        raise PrivilegedActionError("rclone-update accepts no arguments")
    if helper == "xone-dongle-install" and args:
        raise PrivilegedActionError("xone-dongle-install accepts no arguments")
    if helper == "xone-firmware-install" and args:
        raise PrivilegedActionError("xone-firmware-install accepts no arguments")
    if helper == "hardware-setup" and args:
        raise PrivilegedActionError("hardware-setup accepts no arguments")
    if helper == "sleep-mode" and args != ("deep",):
        raise PrivilegedActionError("sleep-mode accepts only deep")
    return PrivilegedAction(
        name=helper,
        argv=(*_prefix(frontend), executable, *args),
    )


def openconnect_action(
    *,
    gateway: str,
    protocol: str,
    os_emulation: str,
    username: str = "",
    usergroup: str = "",
    password_stdin: bool = False,
    cookie: str = "",
) -> PrivilegedAction:
    if protocol not in {"gp", "anyconnect", "pulse", "nc", "f5", "fortinet", "array"}:
        raise PrivilegedActionError(f"Unsupported VPN protocol: {protocol}")
    if os_emulation not in {"win", "linux", "mac"}:
        raise PrivilegedActionError(f"Unsupported VPN OS emulation: {os_emulation}")
    if not gateway or not _SAFE_GATEWAY_RE.fullmatch(gateway):
        raise PrivilegedActionError("VPN gateway contains unsupported characters")
    for field, value in (("username", username), ("usergroup", usergroup), ("cookie", cookie)):
        if any(char in value for char in ("\0", "\n", "\r")):
            raise PrivilegedActionError(f"VPN {field} contains control characters")
    if password_stdin and cookie:
        raise PrivilegedActionError("VPN password stdin and cookie modes are mutually exclusive")

    args = [
        "sudo", "-E", "-A", "/usr/bin/openconnect",
        "--protocol", protocol,
        "--os", os_emulation,
        "--script", "/usr/libexec/kyth-vpnc-script",
    ]
    if password_stdin:
        args.append("--passwd-on-stdin")
    if usergroup:
        args += ["--usergroup", usergroup]
    if cookie:
        args += ["--cookie", cookie]
    if username:
        args += ["--user", username]
    args.append(gateway)
    return PrivilegedAction(
        name="openconnect",
        argv=tuple(args),
        sensitive_options=("--cookie",),
    )


def scheduler_action(name: str) -> PrivilegedAction:
    if not _SAFE_SCHEDULER_RE.fullmatch(name):
        raise PrivilegedActionError(f"Invalid sched-ext scheduler name: {name}")
    return PrivilegedAction(
        name="scheduler-set",
        argv=("sudo", "-n", "/usr/bin/kyth-scx", "set", name),
    )
