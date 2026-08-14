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
from enum import StrEnum
from typing import Any

CommandPart = str | os.PathLike[str]
Command = Sequence[CommandPart]
CompletedTextCommand = subprocess.CompletedProcess[str]

_EXPECTED_COMMAND_ERRORS = (OSError, subprocess.SubprocessError)
_UNSAFE_ENV_PREFIXES = ("LD_", "PYTHON", "PERL", "RUBY", "NODE_", "GEM_", "JAVA_")
_UNSAFE_ENV_NAMES = {"BASH_ENV", "ENV", "GCONV_PATH", "PERL5LIB", "PERL5OPT", "RUBYLIB", "RUBYOPT", "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "NODE_OPTIONS"}
_DESKTOP_ENV_KEYS = frozenset({
    "DBUS_SESSION_BUS_ADDRESS", "DESKTOP_STARTUP_ID", "DISPLAY", "HOME",
    "LANG", "LC_ALL", "PATH", "SUDO_ASKPASS", "WAYLAND_DISPLAY",
    "XAUTHORITY", "XDG_CURRENT_DESKTOP", "XDG_RUNTIME_DIR",
})


class EnvironmentPolicy(StrEnum):
    INHERIT = "inherit"
    SANITIZED = "sanitized"
    DESKTOP = "desktop"


@dataclass(frozen=True)
class CommandSpec:
    """Immutable description of an external process boundary."""

    argv: tuple[str, ...]
    name: str = "command"
    timeout: float | None = 30
    environment: EnvironmentPolicy = EnvironmentPolicy.SANITIZED
    sensitive_options: tuple[str, ...] = ()
    invalidates: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        normalize_command(self.argv)

    def command(self) -> list[str]:
        return list(self.argv)

    def display_command(self) -> list[str]:
        command = self.command()
        for index, value in enumerate(command[:-1]):
            if value in self.sensitive_options:
                command[index + 1] = "<redacted>"
        return command


def command_spec(command: Command | CommandSpec, **kwargs: Any) -> CommandSpec:
    if isinstance(command, CommandSpec):
        if kwargs:
            raise TypeError("cannot override an existing CommandSpec")
        return command
    return CommandSpec(argv=tuple(normalize_command(command)), **kwargs)


def normalize_command(command: Command) -> list[str]:
    """Return *command* as the string list expected by ``subprocess``."""
    if isinstance(command, (str, bytes)):
        raise TypeError("command must be a sequence of arguments, not a shell string")
    if not command:
        raise ValueError("command must contain at least one argument")
    return [os.fspath(part) for part in command]


_UJUST_RECIPE_RE = __import__("re").compile(r"^[a-z0-9][a-z0-9_-]*$")


def ujust_command(recipe: str) -> list[str]:
    """Return a validated ``ujust`` argv without invoking a shell.

    Centralizes the ``ujust <recipe>`` boundary that was previously
    ``[\"bash\", \"-c\", f\"ujust {recipe}\"]`` in several Hub pages.
    The recipe is restricted to ``[a-z0-9_-]`` to prevent argument
    injection; callers must use a literal recipe name, not user input.
    """
    if not recipe or not _UJUST_RECIPE_RE.fullmatch(recipe):
        raise ValueError(f"Refusing unsafe ujust recipe: {recipe!r}")
    return ["ujust", recipe]


def sanitized_environment(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a process environment without loader/interpreter injection."""
    source = os.environ if env is None else env
    return {
        key: value
        for key, value in source.items()
        if key not in _UNSAFE_ENV_NAMES
        and not any(key.startswith(prefix) for prefix in _UNSAFE_ENV_PREFIXES)
    }


def desktop_environment(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Keep only environment needed for desktop session authentication."""
    source = os.environ if env is None else env
    return {key: value for key, value in source.items() if key in _DESKTOP_ENV_KEYS}


def environment_for(
    policy: EnvironmentPolicy,
    env: Mapping[str, str] | None = None,
) -> dict[str, str] | None:
    if policy is EnvironmentPolicy.INHERIT:
        return dict(os.environ if env is None else env)
    if policy is EnvironmentPolicy.DESKTOP:
        return desktop_environment(env)
    return sanitized_environment(env)


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

    def _apply_policy(
        self,
        kwargs: dict[str, Any],
        *,
        bounded: bool,
        spec: CommandSpec | None = None,
    ) -> None:
        if spec is not None or self._policy.enforce_no_shell:
            kwargs.setdefault("shell", False)
        if spec is not None:
            kwargs["env"] = environment_for(spec.environment, kwargs.get("env"))
            if bounded and spec.timeout is not None:
                kwargs.setdefault("timeout", spec.timeout)
        else:
            if self._policy.sanitize_env:
                kwargs["env"] = sanitized_environment(kwargs.get("env"))
            if bounded and self._policy.timeout is not None:
                kwargs.setdefault("timeout", self._policy.timeout)

    def run(self, command: Command | CommandSpec, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        """Run a command without raising solely because it returned non-zero."""
        kwargs.setdefault("check", False)
        spec = command if isinstance(command, CommandSpec) else None
        self._apply_policy(kwargs, bounded=True, spec=spec)
        executor = self._executor or subprocess.run
        return executor(spec.command() if spec else normalize_command(command), **kwargs)

    def spawn(self, command: Command | CommandSpec, **kwargs: Any) -> subprocess.Popen[Any]:
        """Start a process through the same normalization and environment policy."""
        spec = command if isinstance(command, CommandSpec) else None
        self._apply_policy(kwargs, bounded=False, spec=spec)
        spawner = self._spawner or subprocess.Popen
        return spawner(spec.command() if spec else normalize_command(command), **kwargs)

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


def run_quiet(
    command: Command,
    *,
    timeout: float | None = 30,
) -> subprocess.CompletedProcess[Any] | None:
    """Run *command* discarding stdout/stderr, returning None on execution failure.

    Centralizes the repeated ``stdout=DEVNULL, stderr=DEVNULL, check=False``
    pattern used by health checks and notifications so callers do not import
    ``subprocess`` solely for ``DEVNULL``.
    """
    try:
        return DEFAULT_RUNNER.run(
            command,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except _EXPECTED_COMMAND_ERRORS:
        return None
