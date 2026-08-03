"""Qt binding shim — prefers PySide6 (LGPL), falls back to PyQt6 (GPL).

Every Qt symbol used in KythOS GUI components is imported from this module,
allowing applications to remain binding-agnostic.
"""

# pylint: disable=unused-import

import os

__all__ = [
    "QT_BINDING",
    "QApplication", "QMainWindow", "QWidget", "QVBoxLayout", "QHBoxLayout",
    "QPushButton", "QLabel", "QTextEdit", "QStackedWidget", "QProgressBar",
    "QFrame", "QScrollArea", "QFileDialog", "QMessageBox", "QLineEdit",
    "QSizePolicy", "QDialog", "QCheckBox", "QComboBox", "QRadioButton", "QButtonGroup",
    "QDialogButtonBox", "QGridLayout", "QCompleter", "QInputDialog", "QLayout",
    "Qt", "QThread", "Signal", "QTimer", "QUrl", "QLibraryInfo", "QSize", "QRect", "QStringListModel",
    "QDesktopServices", "QIcon", "QKeySequence", "QShortcut", "QAction",
    "QDBusConnection", "QDBusInterface",
    "QLocalServer", "QLocalSocket",
    "QWebEngineView", "QWebEnginePage", "QWebEngineProfile", "QWebEngineUrlScheme",
    "QWebEngineUrlSchemeHandler", "QWebEngineUrlRequestJob", "QWebEngineScript",
    "_WEBENGINE_AVAILABLE",
    "single_shot",
]

# Must be set before any Qt WebEngine module is imported or initialized.
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-dev-shm-usage")

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTextEdit, QStackedWidget, QProgressBar,
        QFrame, QScrollArea, QFileDialog, QMessageBox, QLineEdit,
        QSizePolicy, QDialog, QCheckBox, QComboBox, QRadioButton, QButtonGroup,
        QDialogButtonBox, QGridLayout, QCompleter, QInputDialog, QLayout,
    )
    from PySide6.QtCore import (
        Qt, QThread, Signal, QTimer, QUrl, QLibraryInfo, QSize, QRect, QStringListModel,
    )
    from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut, QAction
    from PySide6.QtDBus import QDBusConnection, QDBusInterface
    from PySide6.QtNetwork import QLocalServer, QLocalSocket

    QT_BINDING = "PySide6"
except ImportError:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTextEdit, QStackedWidget, QProgressBar,
        QFrame, QScrollArea, QFileDialog, QMessageBox, QLineEdit,
        QSizePolicy, QDialog, QCheckBox, QComboBox, QRadioButton, QButtonGroup,
        QDialogButtonBox, QGridLayout, QCompleter, QInputDialog, QLayout,
    )
    from PyQt6.QtCore import (
        Qt, QThread, QTimer, QUrl, QLibraryInfo, QSize, QRect, QStringListModel,
    )
    from PyQt6.QtCore import pyqtSignal as Signal
    from PyQt6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut, QAction
    from PyQt6.QtDBus import QDBusConnection, QDBusInterface
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket

    QT_BINDING = "PyQt6"

QWebEngineView = None
QWebEnginePage = None
QWebEngineProfile = None
QWebEngineUrlScheme = None
QWebEngineUrlSchemeHandler = None
QWebEngineUrlRequestJob = None
QWebEngineScript = None
_WEBENGINE_AVAILABLE = False

try:
    if QT_BINDING == "PySide6":
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import (
            QWebEnginePage,
            QWebEngineProfile,
            QWebEngineUrlScheme,
            QWebEngineUrlSchemeHandler,
            QWebEngineUrlRequestJob,
            QWebEngineScript,
        )
    else:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import (
            QWebEnginePage,
            QWebEngineProfile,
            QWebEngineUrlScheme,
            QWebEngineUrlSchemeHandler,
            QWebEngineUrlRequestJob,
            QWebEngineScript,
        )
    for _gp_scheme in (b"globalprotectcallback", b"gc"):
        _s = QWebEngineUrlScheme(_gp_scheme)
        _s.setFlags(
            QWebEngineUrlScheme.Flag.SecureScheme |
            QWebEngineUrlScheme.Flag.ContentSecurityPolicyIgnored
        )
        QWebEngineUrlScheme.registerScheme(_s)
    _WEBENGINE_AVAILABLE = True
except ImportError:
    pass


def single_shot(parent, ms: int, slot):
    """QTimer.singleShot(ms, slot) that stays alive as a real, parented QTimer.

    QTimer.singleShot(ms, callable) routes through PyQt6's internal
    PyQtSlotProxy helper object, which has been observed to segfault with a
    use-after-free (SIGSEGV in PyQtSlotProxy::qt_metacall -> QObject::deleteLater)
    on newer CPython builds. A QTimer parented to a real, long-lived QObject
    sidesteps that code path entirely via normal Qt ownership/signal-slot.
    """
    timer = QTimer(parent)
    timer.setSingleShot(True)
    timer.timeout.connect(slot)
    timer.start(ms)
    return timer
