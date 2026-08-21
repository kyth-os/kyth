"""QML bridge stub — Phase 3.

Exposes Python services to QML via QQmlContext without rewriting probes.
Today it is a no-op import guard; when window.py opts into QQuickWidget,
import this and set contextProperty("Kyth", bridge).

Keeps the decision: Python stays the privileged orchestrator, QML is view.
Uses the same Qt binding preference as the rest of System Hub (PySide6 via
kyth_shared.qt), not a PyQt6-first import path.
"""
from __future__ import annotations

try:
    from kyth_shared.qt import QObject
except (OSError, ValueError, RuntimeError, AttributeError, ImportError, KeyError):  # noqa: BLE001
    QObject = object  # type: ignore[misc, assignment]


class QmlBridge(QObject if isinstance(QObject, type) else object):  # type: ignore[misc]
    def __init__(self, parent=None):
        try:
            super().__init__(parent)  # type: ignore[call-arg]
        except (OSError, ValueError, RuntimeError, AttributeError, TypeError, KeyError):  # noqa: BLE001
            pass
        self._version = "qml-bridge-stub"

    def version(self) -> str:
        return self._version
