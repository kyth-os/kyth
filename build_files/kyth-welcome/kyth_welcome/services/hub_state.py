"""Centralized Hub state store — thin shared dict for workers/profile/catalog.

Pages currently keep per-page `self._fp_*`, `self._data_workers`, `self._profile`
dicts. This module provides a single place for cross-page state that survives
navigation, avoids duplicate `DataWorker` caches, and lets `TaskSupervisor`
remain the single owner for lifecycle. Pages may still keep UI-only state
locally; only shared, cacheable data goes here.
"""
from __future__ import annotations

from typing import Any

# Fallback if Qt not available (tests without PySide)
try:
    from PySide6.QtCore import QObject as _QObject, Signal as _Signal
    Base = _QObject
    Sig = _Signal
except Exception:
    try:
        from PyQt6.QtCore import QObject as _QObject, pyqtSignal as _Signal
        Base = _QObject
        Sig = _Signal
    except Exception:
        Base = object  # type: ignore[assignment]
        def Sig(*a, **kw):  # type: ignore[no-redef]
            return None


class HubState(Base if Base is not object else object):  # type: ignore[misc]
    """In-memory store for Hub-wide cached data.

    Use `get`/`set` for simple cache, `profile` for the current role preset.
    Emits `changed` when a key is updated so pages can subscribe.
    """

    changed = Sig(str) if Base is not object else None  # type: ignore[assignment]

    def __init__(self):
        # QObject init if available
        try:
            super().__init__()  # type: ignore[call-arg]
        except Exception:
            pass
        self._store: dict[str, Any] = {}
        self._profile: str = "everyday"

    @property
    def profile(self) -> str:
        return self._profile

    @profile.setter
    def profile(self, value: str) -> None:
        if value != self._profile:
            self._profile = value
            self._store["profile"] = value
            try:
                if self.changed is not None:
                    self.changed.emit("profile")  # type: ignore[attr-defined]
            except Exception:
                pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value
        try:
            if self.changed is not None:
                self.changed.emit(key)  # type: ignore[attr-defined]
        except Exception:
            pass

    def clear(self, key: str) -> None:
        self._store.pop(key, None)
        try:
            if self.changed is not None:
                self.changed.emit(key)  # type: ignore[attr-defined]
        except Exception:
            pass


# Singleton for the running Hub process
HUB_STATE = HubState()
