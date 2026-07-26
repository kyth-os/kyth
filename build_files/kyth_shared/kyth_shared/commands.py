"""Consistent subprocess execution for KythOS services and command-line tools.

The helpers in this module deliberately stay close to :mod:`subprocess`.
Callers still choose their command-specific arguments and error policy, while
sharing the mechanics for normalization, default ``check=False`` behavior,
captured text output, and expected operating-system failures.
"""
from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

CommandPart = str | os.PathLike[str]
Command = Sequence[CommandPart]
CompletedTextCommand = subprocess.CompletedProcess[str]

_EXPECTED_COMMAND_ERRORS = (OSError, subprocess.SubprocessError)
_UNSAFE_ENV_PREFIXES = ("LD_", "PYTHON")
_UNSAFE_ENV_NAMES = {"BASH_ENV", "ENV", "GCONV_PATH", "PERL5LIB", "RUBYLIB"}


def normalize_command(command: Command) -> list[str]:
    """Return *command* as the string list expected by ``subprocess``."""
    if isinstance(command, (str, bytes)):
        raise TypeError("command must be a sequence of arguments, not a shell string")
    if not command:
        raise ValueError("command must contain at least one argument")
    return [os.fspath(part) for part in command]


def sanitized_environment(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a process environment without loader/interpreter injection."""
    source = os.environ if env is None else env
    return {
        key: value
        for key, value in source.items()
        if key not in _UNSAFE_ENV_NAMES
        and not any(key.startswith(prefix) for prefix in _UNSAFE_ENV_PREFIXES)
    }


@dataclass(frozen=True)
class ExecutionPolicy:
    """Defaults for an application-facing command boundary."""

    timeout: float | None = 30
    sanitize_env: bool = True
    enforce_no_shell: bool = True


class CommandRunner:
    """Small injectable facade over :func:`subprocess.run`.

    ``executor`` is primarily useful to tests and specialized callers. Leaving
    it unset resolves ``subprocess.run`` at call time, so normal mocking and
    instrumentation continue to work.
    """

    def __init__(
        self,
        executor: Any | None = None,
        *,
        spawner: Any | None = None,
        policy: ExecutionPolicy | None = None,
    ) -> None:
        self._executor = executor
        self._spawner = spawner
        self._policy = policy or ExecutionPolicy(
            timeout=None,
            sanitize_env=False,
            enforce_no_shell=False,
        )

    def _apply_policy(self, kwargs: dict[str, Any], *, bounded: bool) -> None:
        if self._policy.enforce_no_shell:
            kwargs.setdefault("shell", False)
        if self._policy.sanitize_env:
            kwargs["env"] = sanitized_environment(kwargs.get("env"))
        if bounded and self._policy.timeout is not None:
            kwargs.setdefault("timeout", self._policy.timeout)

    def run(self, command: Command, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        """Run a command without raising solely because it returned non-zero."""
        kwargs.setdefault("check", False)
        self._apply_policy(kwargs, bounded=True)
        executor = self._executor or subprocess.run
        return executor(normalize_command(command), **kwargs)

    def spawn(self, command: Command, **kwargs: Any) -> subprocess.Popen[Any]:
        """Start a process through the same normalization and environment policy."""
        self._apply_policy(kwargs, bounded=False)
        spawner = self._spawner or subprocess.Popen
        return spawner(normalize_command(command), **kwargs)

    def optional(
        self,
        command: Command,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[Any] | None:
        """Run a command, returning ``None`` for expected execution failures."""
        try:
            return self.run(command, **kwargs)
        except _EXPECTED_COMMAND_ERRORS:
            return None

    def text(
        self,
        command: Command,
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CompletedTextCommand | None:
        """Run a command and capture decoded stdout/stderr, if it can execute."""
        kwargs: dict[str, Any] = {
            "capture_output": True,
            "text": True,
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        if env is not None:
            kwargs["env"] = env
        result = self.optional(command, **kwargs)
        return result

    def stdout(
        self,
        command: Command,
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
        strip: bool = True,
    ) -> str:
        """Return captured stdout, or an empty string if execution failed."""
        result = self.text(command, timeout=timeout, env=env)
        if result is None:
            return ""
        return result.stdout.strip() if strip else result.stdout


DEFAULT_RUNNER = CommandRunner()
APPLICATION_RUNNER = CommandRunner(policy=ExecutionPolicy())


def run(command: Command, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    """Run *command* through the shared default runner."""
    return DEFAULT_RUNNER.run(command, **kwargs)


def run_optional(
    command: Command,
    **kwargs: Any,
) -> subprocess.CompletedProcess[Any] | None:
    """Run *command*, returning ``None`` if the process could not execute."""
    return DEFAULT_RUNNER.optional(command, **kwargs)


def run_text(
    command: Command,
    *,
    timeout: float | None = None,
    env: Mapping[str, str] | None = None,
) -> CompletedTextCommand | None:
    """Capture text output from *command* through the default runner."""
    return DEFAULT_RUNNER.text(command, timeout=timeout, env=env)


def command_stdout(
    command: Command,
    *,
    timeout: float | None = None,
    env: Mapping[str, str] | None = None,
    strip: bool = True,
) -> str:
    """Return captured stdout from *command* through the default runner."""
    return DEFAULT_RUNNER.stdout(
        command,
        timeout=timeout,
        env=env,
        strip=strip,
    )
