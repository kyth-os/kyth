"""QML bridge stub — Phase 3.

Exposes Python services to QML via QQmlContext without rewriting probes.
Today it is a no-op import guard; when window.py opts into QQuickWidget,
import this and set contextProperty("Kyth", bridge).

Keeps the decision: Python stays the privileged orchestrator, QML is view.
"""
from __future__ import annotations

try:
    from PyQt6.QtCore import QObject
except Exception:
    QObject = object  # type: ignore
    pyqtProperty = lambda *a, **k: property(lambda s: None)  # type: ignore
    pyqtSignal = lambda *a, **k: None  # type: ignore

class QmlBridge(QObject if isinstance(QObject, type) else object):  # type: ignore[misc]
    def __init__(self, parent=None):
        try:
            super().__init__(parent)  # type: ignore[call-arg]
        except Exception:
            pass
        self._version = "qml-bridge-stub"

    def version(self) -> str:
        return self._version
