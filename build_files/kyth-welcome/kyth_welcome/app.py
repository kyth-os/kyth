import atexit
import os
import sys
import traceback
from pathlib import Path

_LOCK_FILE = Path.home() / ".cache" / "kyth" / "kyth-welcome.lock"


def _acquire_lock() -> bool:
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        if _LOCK_FILE.exists():
            pid_text = _LOCK_FILE.read_text().strip()
            if pid_text.isdigit():
                pid = int(pid_text)
                try:
                    os.kill(pid, 0)
                    return False  # already running
                except (ProcessLookupError, PermissionError):
                    pass  # stale lock
        _LOCK_FILE.write_text(str(os.getpid()))
        atexit.register(_LOCK_FILE.unlink, missing_ok=True)
        return True
    except OSError:
        return True  # can't lock → allow launch

# __KYTH_GENERATED_IMPORTS__
from .core_base import (
    _IS_LIVE, _is_first_run, _prefer_xwayland_if_wayland_plugin_missing, _remove_autostart, _shutdown_threads,
    _wait_for_display_setup,
)
from .qt import (
    QApplication, QIcon,
)
from .theme import (
    QSS,
)
from .windows import MainWindow
from .wizard import WizardWindow


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    if not _acquire_lock():
        sys.exit(0)

    # Parse --page PAGEKEY before QApplication (which may strip unrecognised args)
    start_page = None
    raw_args = sys.argv[1:]
    for i, a in enumerate(raw_args):
        if a == "--page" and i + 1 < len(raw_args):
            start_page = raw_args[i + 1]

    _wait_for_display_setup()
    _prefer_xwayland_if_wayland_plugin_missing()

    # PyQt6 calls qFatal() (abort + core dump) on any uncaught Python exception
    # in a slot unless an excepthook is installed. Log and keep the app alive.
    def _log_uncaught(exc_type, exc_value, exc_tb):
        traceback.print_exception(exc_type, exc_value, exc_tb, file=sys.stderr)
    sys.excepthook = _log_uncaught

    app = QApplication(sys.argv)
    # Join background probe threads before Qt tears down: destroying a running
    # QThread aborts the process, turning a normal quit into a crash.
    app.aboutToQuit.connect(_shutdown_threads)
    app.setApplicationName("kyth-welcome")
    app.setDesktopFileName("kyth-welcome")
    app.setWindowIcon(QIcon.fromTheme("kyth"))
    app.setStyleSheet(QSS)

    if _IS_LIVE:
        win = MainWindow()
    elif _is_first_run():
        win = WizardWindow()
    else:
        win = MainWindow()
    win.setWindowIcon(QIcon.fromTheme("kyth"))
    win.showMaximized()
    if start_page and isinstance(win, MainWindow):
        win._navigate_to(start_page)
    _remove_autostart()
    sys.exit(app.exec())
