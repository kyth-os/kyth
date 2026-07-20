from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass


LogFn = Callable[[str], None]
_SAFE_DEVICE_ARG_RE = re.compile(r"^/dev/[A-Za-z0-9._/+:-]+$")


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


def run_command(
    argv: Sequence[object],
    *,
    log: LogFn | None = None,
    description: str | None = None,
    timeout: int | None = None,
    **kwargs,
):
    if isinstance(argv, (str, bytes)):
        raise TypeError("argv must be a sequence of arguments, not a shell command string")
    command = [_validate_command_arg(str(part)) for part in argv]
    if not command or not command[0]:
        raise ValueError("argv must contain a non-empty executable")
    if kwargs.pop("shell", False):
        raise ValueError("shell execution is forbidden for installer commands")
    label = description or _format_command(command)
    if log is not None:
        log(f"$ {_format_command(command)}")

    try:
        # Commands are assembled by trusted installer code, passed as an argv
        # vector, and never interpreted by a shell. User-controlled disk names
        # and labels can therefore only be arguments, not executable syntax.
        # codeql[py/command-line-injection]
        return subprocess.run(command, timeout=timeout, shell=False, **kwargs)  # nosec B603 # nosemgrep
    except subprocess.CalledProcessError as exc:
        detail = f"{label} failed with exit code {exc.returncode}"
        if exc.stdout:
            detail += f"\n{exc.stdout}"
        raise RuntimeError(detail) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{label} timed out after {exc.timeout} seconds") from exc


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
