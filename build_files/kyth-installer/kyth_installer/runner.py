from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass


LogFn = Callable[[str], None]


@dataclass(frozen=True)
class InstallerCommand:
    argv: tuple[str, ...]
    description: str
    timeout: int | None = None


def _format_command(argv: Sequence[object]) -> str:
    return " ".join(str(part) for part in argv)


def run_command(
    argv: Sequence[object],
    *,
    log: LogFn | None = None,
    description: str | None = None,
    timeout: int | None = None,
    **kwargs,
):
    command = [str(part) for part in argv]
    label = description or _format_command(command)
    if log is not None:
        log(f"$ {_format_command(command)}")

    try:
        return subprocess.run(command, timeout=timeout, **kwargs)
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
