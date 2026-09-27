"""Explicit privileged-operation adapter for the installer service.

The Tauri shell is deliberately not an executor.  It can request the frozen
HTTP/SSE API, while this adapter is the only phase-facing boundary for
commands that must run in the privileged Python service.  Callers provide a
typed command description; the adapter applies the service's root boundary
and never invokes a shell.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ExecutorCommand:
    """A command owned by a privileged installer phase."""

    argv: tuple[str, ...]
    description: str
    timeout: int | None = 30
    as_root: bool = True

    @classmethod
    def from_argv(
        cls,
        argv: Sequence[object],
        description: str,
        *,
        timeout: int | None = 30,
        as_root: bool = True,
    ) -> "ExecutorCommand":
        if isinstance(argv, (str, bytes)):
            raise TypeError("executor command requires argv, not shell text")
        values = tuple(str(part) for part in argv)
        if not values or not values[0]:
            raise ValueError("executor command must contain an executable")
        return cls(values, description, timeout, as_root)


class PrivilegedExecutor:
    """Adapt typed phase operations to the validated Python runner.

    ``run_command`` and ``stream_runner`` are injected so phase tests can
    replace them without bypassing this boundary.  The adapter does not
    accept shell strings, and all command validation remains in
    :mod:`kyth_installer.runner`.
    """

    def __init__(
        self,
        *,
        run_command: Callable[..., Any] | None,
        as_root: Callable[[list[str]], list[str]],
        stream_runner_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._run_command = run_command
        self._as_root = as_root
        self._stream_runner_factory = stream_runner_factory

    def _argv(self, command: ExecutorCommand) -> list[str]:
        argv = list(command.argv)
        return self._as_root(argv) if command.as_root else argv

    def run(self, command: ExecutorCommand, **kwargs: Any) -> Any:
        """Run one explicitly-owned command through the validated runner."""
        if self._run_command is None:
            raise RuntimeError("scalar executor is not configured")
        kwargs.setdefault("timeout", command.timeout)
        kwargs.setdefault("description", command.description)
        return self._run_command(self._argv(command), **kwargs)

    def stream(
        self,
        command: ExecutorCommand,
        *,
        rx_bytes: Callable[[], int],
        publish: Callable[[dict], None],
        pct_start: int,
        pct_end: int,
        log: Callable[[str], None],
        progress: Callable[[int], None],
        **kwargs: Any,
    ) -> None:
        """Run a bounded streaming operation through the same boundary."""
        if self._stream_runner_factory is None:
            raise RuntimeError("streaming executor is not configured")
        runner = self._stream_runner_factory(rx_bytes=rx_bytes, publish=publish)
        runner.run(
            self._argv(command),
            pct_start,
            pct_end,
            log,
            progress,
            **kwargs,
        )
