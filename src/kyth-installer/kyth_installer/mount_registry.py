"""Mount registry as LIFO stack — single cleanup entry point."""

from __future__ import annotations

import contextlib


class MountRegistry:
    """LIFO stack for installer mounts. Push on mount, pop on unmount.

    `register` is idempotent, `release` removes first occurrence from top,
    `cleanup` unmounts in LIFO order via provided `run` callable.
    """

    def __init__(self):
        self._stack: list[str] = []

    def register(self, path: str) -> None:
        if path not in self._stack:
            self._stack.append(path)

    def release(self, path: str) -> None:
        # Remove from top-most occurrence
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i] == path:
                del self._stack[i]
                break

    def snapshot(self) -> list[str]:
        return list(self._stack)

    def clear(self) -> None:
        self._stack.clear()

    @contextlib.contextmanager
    def hold(self, path: str, *, run=None, log=None):
        """Context manager: register on enter, cleanup on exit."""
        self.register(path)
        try:
            yield
        finally:
            if run is not None:
                try:
                    from .system import _safe_umount

                    _safe_umount(run, path, check=True)
                except (OSError, RuntimeError, ValueError) as exc:  # noqa: BLE001 -- narrow: umount failures
                    if log:
                        log(f"Warning: could not unmount {path}: {exc}")
            self.release(path)

    def cleanup(self, *, run, log=None) -> None:
        """Unmount all in LIFO order."""
        for path in reversed(self.snapshot()):
            try:
                from .system import _safe_umount

                _safe_umount(run, path, check=True)
            except (OSError, RuntimeError, ValueError) as exc:  # noqa: BLE001 -- narrow: umount failures
                if log:
                    log(f"Warning: could not unmount {path}: {exc}")
            self.release(path)
