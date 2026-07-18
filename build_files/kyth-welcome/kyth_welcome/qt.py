"""Qt binding shim — prefers PySide6 (LGPL), falls back to PyQt6 (GPL).

Every Qt symbol used in kyth-welcome is imported from this module, so the
rest of the package is binding-agnostic and the binding can be swapped by
changing the image's installed RPM, not the code.
"""

# pylint: disable=unused-import
# Every symbol below is a deliberate re-export for the rest of the package
# to import from `.qt` — this module has no internal users of its own.

import os

# Must be set before any Qt WebEngine module is imported or initialized.
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-dev-shm-usage")

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTextEdit, QStackedWidget, QProgressBar,
        QFrame, QScrollArea, QFileDialog, QMessageBox, QLineEdit,
        QSizePolicy, QDialog, QCheckBox, QComboBox, QRadioButton, QButtonGroup,
        QDialogButtonBox, QGridLayout, QCompleter, QInputDialog,
    )
    from PySide6.QtCore import (
        Qt, QThread, Signal, QTimer, QUrl, QLibraryInfo, QSize, QStringListModel,
    )
    from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
    from PySide6.QtDBus import QDBusConnection, QDBusInterface

    QT_BINDING = "PySide6"
except ImportError:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTextEdit, QStackedWidget, QProgressBar,
        QFrame, QScrollArea, QFileDialog, QMessageBox, QLineEdit,
        QSizePolicy, QDialog, QCheckBox, QComboBox, QRadioButton, QButtonGroup,
        QDialogButtonBox, QGridLayout, QCompleter, QInputDialog,
    )
    from PyQt6.QtCore import (
        Qt, QThread, QTimer, QUrl, QLibraryInfo, QSize, QStringListModel,
    )
    from PyQt6.QtCore import pyqtSignal as Signal
    from PyQt6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
    from PyQt6.QtDBus import QDBusConnection, QDBusInterface

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
