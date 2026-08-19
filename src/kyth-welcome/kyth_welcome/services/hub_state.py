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

    # --- Control-plane extensions (progressive vs Bazzite/Portal) ---
    # Hub as OS control plane: track staged/rollback/repair state so
    # RepairPage and UpdatePage share one source of truth instead of
    # per-page bootc spawns.

    def set_update_status(self, status: str, detail: str = "") -> None:
        self.set("update_status", {"status": status, "detail": detail})

    def get_update_status(self) -> dict[str, str]:
        return self.get("update_status", {"status": "idle", "detail": ""})

    def set_rollback_available(self, available: bool) -> None:
        self.set("rollback_available", available)

    def is_rollback_available(self) -> bool:
        return bool(self.get("rollback_available", False))

    def set_repair_plan(self, plan: dict[str, Any] | None) -> None:
        if plan is None:
            self.clear("repair_plan")
        else:
            self.set("repair_plan", plan)

    def get_repair_plan(self) -> dict[str, Any] | None:
        return self.get("repair_plan")


def rollback_available_from_probe() -> bool:
    """Single-source rollback check — reads staged+rollback from probe cache, not per-page bootc spawn."""
    try:
        from kyth_shared.system.probe import read_section

        data = read_section("bootc-status-data", max_age=90)
        if isinstance(data, dict):
            status = data.get("status") or {}
            has_staged = status.get("staged") is not None
            has_rollback = status.get("rollback") is not None
            return bool(has_staged or has_rollback)
    except Exception:
        pass
    return False


# Singleton for the running Hub process
HUB_STATE = HubState()
