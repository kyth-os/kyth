#!/usr/bin/env python3
"""Atheris fuzz target for pure Kyth System Hub parsers."""

from __future__ import annotations

import os
import pathlib
import sys
import types


def _install_qt_stubs() -> None:
    class _Dummy:
        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, *args, **kwargs):
            return self

        def __getattr__(self, _name):
            return self

    class _DummySignal(_Dummy):
        pass

    class _DummyLibraryInfo:
        class LibraryPath:
            PluginsPath = 0

        @staticmethod
        def path(_which):
            return ""

    qt = types.ModuleType("kyth_welcome.qt")
    for name in (
        "QComboBox",
        "QDialog",
        "QFrame",
        "QHBoxLayout",
        "QLabel",
        "QLineEdit",
        "QPushButton",
        "QSizePolicy",
        "QTextEdit",
        "QThread",
        "QTimer",
        "QUrl",
        "QVBoxLayout",
        "QWebEnginePage",
        "QWebEngineProfile",
        "QWebEngineUrlRequestJob",
        "QWebEngineUrlSchemeHandler",
        "QWebEngineView",
        "QWidget",
    ):
        setattr(qt, name, _Dummy)
    qt.Signal = _DummySignal
    qt.QLibraryInfo = _DummyLibraryInfo
    qt._WEBENGINE_AVAILABLE = False
    # Fill any other Qt symbols that kyth_shared.qt exports (e.g. single_shot)
    # so `from kyth_welcome.qt import single_shot` works without hard-coding
    # the full __all__ in two places. The _Dummy fallback covers future adds.
    for _name in (
        "QT_BINDING",
        "QApplication",
        "QMainWindow",
        "QStackedWidget",
        "QProgressBar",
        "QScrollArea",
        "QFileDialog",
        "QMessageBox",
        "QCheckBox",
        "QRadioButton",
        "QButtonGroup",
        "QDialogButtonBox",
        "QGridLayout",
        "QCompleter",
        "QInputDialog",
        "QLayout",
        "QListWidget",
        "QListWidgetItem",
        "Qt",
        "QSize",
        "QRect",
        "QStringListModel",
        "QDesktopServices",
        "QIcon",
        "QKeySequence",
        "QShortcut",
        "QAction",
        "QDBusConnection",
        "QDBusInterface",
        "QLocalServer",
        "QLocalSocket",
        "QWebEngineUrlScheme",
        "QWebEngineScript",
        "single_shot",
    ):
        if not hasattr(qt, _name):
            setattr(qt, _name, _Dummy if _name != "Signal" else _DummySignal)
    # PEP 562 fallback for any future import not listed above
    def _qt_getattr(name: str):  # type: ignore[no-redef]
        return _Dummy if name != "Signal" else _DummySignal

    qt.__getattr__ = _qt_getattr  # type: ignore[attr-defined]
    sys.modules["kyth_welcome.qt"] = qt

    widgets = types.ModuleType("kyth_welcome.widgets")
    widgets.Page = _Dummy
    widgets._make_card = lambda *args, **kwargs: (_Dummy(), _Dummy())
    widgets._set_log_panel = lambda *args, **kwargs: None
    sys.modules["kyth_welcome.widgets"] = widgets


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))
_install_qt_stubs()

from kyth_welcome.services import gaming, hardware  # noqa: E402


def _exercise(text: str) -> None:
    display = hardware._parse_kscreen_output(text)
    assert isinstance(display.summary, str)
    assert isinstance(display.details, str)
    assert isinstance(display.status, str)

    mode = hardware._format_display_mode(text)
    assert isinstance(mode, str)

    acf = gaming._parse_steam_acf_text(text)
    assert isinstance(acf, dict)


def TestOneInput(data: bytes) -> None:
    # LLVMFuzzerTestOneInput-compatible entry point for ClusterFuzzLite.
    text = data.decode("utf-8", errors="replace")
    _exercise(text[:8192])


def _smoke() -> None:
    cases = (
        b"",
        b'Output: 1 HDMI-A-1\nconnected\nenabled\nModes: 0:1920x1080@144*! 1:1280x720@60\nVrr: Never\nHdr: disabled\n',
        b'Output: 1 DP-1\nconnected\nenabled\nModes: 0:1920x1080@..\nVrr: never\n',
        b'"appid" "123"\n"name" "Portal 2"\n"installdir" "Portal 2"\n',
    )
    for case in cases:
        TestOneInput(case)


if __name__ == "__main__":
    if os.environ.get("KYTH_FUZZ_SMOKE") == "1":
        _smoke()
    else:
        import atheris

        atheris.Setup(sys.argv, TestOneInput)
        atheris.Fuzz()
