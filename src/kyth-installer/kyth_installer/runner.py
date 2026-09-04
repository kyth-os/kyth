from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass


LogFn = Callable[[str], None]
_SAFE_DEVICE_ARG_RE = re.compile(r"^/dev/[A-Za-z0-9._/+:-]+$")
_SAFE_USERNAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*[$]?$")
_SAFE_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Z_][A-Z0-9_]*=.*$")

# Keep the process boundary narrow: these are the only programs the installer
# invokes. Arguments remain dynamic (disk paths, labels, image references), but
# callers cannot turn one of those values into a different executable.
_ALLOWED_EXECUTABLES = frozenset({
    "blkid",
    "blockdev",
    "bootc",
    "btrfs",
    "cat",
    "chmod",
    "chown",
    "chromium",
    "chromium-bin",
    "chromium-browser",
    "cp",
    "e2fsck",
    "echo",
    "efibootmgr",
    "false",
    "findmnt",
    "ip",
    "kyth-installer-exec",
    "kyth-installer-native",
    "kyth-installer-shell",
    "kyth-installerd",
    "ln",
    "lsblk",
    "mkdir",
    "mkfs.btrfs",
    "mkfs.ext4",
    "mkfs.fat",
    "mkfs.xfs",
    "mokutil",
    "mount",
    "mkswap",
    "ntfsresize",
    "openssl",
    "parted",
    "partprobe",
    "resize2fs",
    "restorecon",
    "sgdisk",
    "sudo",
    "sync",
    "systemctl",
    "tee",
    "test",
    "timedatectl",
    "true",
    "udevadm",
    "umount",
    "useradd",
})
_TRUSTED_EXECUTABLE_DIRS = frozenset(
    os.path.realpath(path) for path in ("/bin", "/sbin", "/usr/bin", "/usr/sbin")
)


def run_as_root(cmd: list[str]) -> list[str]:
    """Centralized privilege-escalation helper (was duplicated in system.py).

    Returns `cmd` unchanged when already root, otherwise prepends `sudo -n`.
    """
    return cmd if os.geteuid() == 0 else ["sudo", "-n", *cmd]


@dataclass(frozen=True)
class InstallerCommand:
    argv: tuple[str, ...]
    description: str
    timeout: int | None = None


def _format_command(argv: Sequence[object]) -> str:
    return " ".join(str(part) for part in argv)


def _validate_command_arg(arg: str) -> str:
    if not arg:
        raise RuntimeError("Refusing to execute command with empty argument.")
    if "\x00" in arg or "\n" in arg or "\r" in arg:
        raise RuntimeError("Refusing to execute command with control characters in arguments.")

    if arg.startswith("/dev/"):
        real = os.path.realpath(arg)
        if not real.startswith("/dev/") or not _SAFE_DEVICE_ARG_RE.fullmatch(real):
            raise RuntimeError(f"Refusing unsafe device path argument: {arg}")
        return real

    return arg


def _validate_executable(executable: str) -> str:
    name = os.path.basename(executable)
    if name not in _ALLOWED_EXECUTABLES:
        raise RuntimeError(f"Refusing unapproved installer executable: {executable}")

    if "/" not in executable:
        return executable

    real = os.path.realpath(executable)
    if (
        os.path.dirname(real) not in _TRUSTED_EXECUTABLE_DIRS
        or os.path.basename(real) not in _ALLOWED_EXECUTABLES
    ):
        raise RuntimeError(f"Refusing executable outside trusted system paths: {executable}")
    return real


def _validate_sudo_command(command: list[str]) -> None:
    """Validate the executable hidden behind the two sudo forms we use."""
    if command[0] != "sudo":
        return

    if len(command) >= 3 and command[1] == "-n":
        command[2] = _validate_executable(command[2])
        return

    if (
        len(command) >= 6
        and command[1] == "-u"
        and _SAFE_USERNAME_RE.fullmatch(command[2])
        and command[3] == "env"
    ):
        nested_index = 4
        while (
            nested_index < len(command)
            and _SAFE_ENV_ASSIGNMENT_RE.fullmatch(command[nested_index])
        ):
            nested_index += 1
        if nested_index < len(command):
            command[nested_index] = _validate_executable(command[nested_index])
            return

    raise RuntimeError("Refusing unsupported sudo command form.")


def prepare_command(argv: Sequence[object]) -> list[str]:
    if isinstance(argv, (str, bytes)):
        raise TypeError("argv must be a sequence of arguments, not a shell command string")
    command = [_validate_command_arg(str(part)) for part in argv]
    if not command or not command[0]:
        raise ValueError("argv must contain a non-empty executable")
    command[0] = _validate_executable(command[0])
    _validate_sudo_command(command)
    return command


def run_command(
    argv: Sequence[object],
    *,
    log: LogFn | None = None,
    description: str | None = None,
    timeout: int | None = 30,
    **kwargs,
):
    command = prepare_command(argv)
    if kwargs.pop("shell", False):
        raise ValueError("shell execution is forbidden for installer commands")
    label = description or _format_command(command)
    if log is not None:
        log(f"$ {_format_command(command)}")

    # check is caller-controlled: most callers pass check=True/False explicitly
    # and rely on the CalledProcessError handling below or their own returncode
    # inspection. Default to False (subprocess.run's own default) only when a
    # caller hasn't opted in, so this stays a no-op for every existing caller.
    kwargs.setdefault("check", False)

    try:
        # Commands are assembled by trusted installer code, passed as an argv
        # vector, and never interpreted by a shell. User-controlled disk names
        # and labels can therefore only be arguments, not executable syntax.
        # check= is always present via the kwargs.setdefault above, just not
        # visible to ruff as a literal keyword here.
        # codeql[py/command-line-injection]
        return subprocess.run(command, timeout=timeout, shell=False, **kwargs)  # nosec B603 # nosemgrep # noqa: PLW1510
    except subprocess.CalledProcessError as exc:
        detail = f"{label} failed with exit code {exc.returncode}"
        if exc.stdout:
            detail += f"\n{exc.stdout}"
        raise RuntimeError(detail) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{label} timed out after {exc.timeout} seconds") from exc


def spawn_command(argv: Sequence[object], **kwargs) -> subprocess.Popen:
    """Start a validated argv command without invoking a shell."""
    if kwargs.pop("shell", False):
        raise ValueError("shell execution is forbidden for installer commands")
    return subprocess.Popen(  # nosec B603 # nosemgrep
        prepare_command(argv), shell=False, **kwargs
    )


def run_installer_command(
    command: InstallerCommand,
    *,
    log: LogFn | None = None,
    **kwargs,
):
    return run_command(
        command.argv,
        log=log,
        description=command.description,
        timeout=command.timeout,
        **kwargs,
    )
