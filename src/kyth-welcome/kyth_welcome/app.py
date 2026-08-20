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

# Hub windows are lazy-imported inside main() to keep cold import cheap
# (windows.py is 709 LOC and pulls heavy page deps). See optimization-budgets.
from .core_base import IS_LIVE, is_first_run, prefer_xwayland_if_wayland_plugin_missing, remove_autostart, wait_for_display_setup
from .services.runtime import shutdown_threads
from .qt import (
    QApplication, QIcon,
)
from .theme import (
    QSS,
)


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

    wait_for_display_setup()
    prefer_xwayland_if_wayland_plugin_missing()

    # PyQt6 calls qFatal() (abort + core dump) on any uncaught Python exception
    # in a slot unless an excepthook is installed. Log and keep the app alive.
    # Also surface to Diagnostics probe via the launcher log and a timestamped
    # error marker the Diagnostics page can surface.
    def _log_uncaught(exc_type, exc_value, exc_tb):
        traceback.print_exception(exc_type, exc_value, exc_tb, file=sys.stderr)
        # Ensure the launcher log (stderr) is flushed for _system_hub_probe
        try:
            sys.stderr.flush()
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            pass
        # Also append a concise marker to the cache error file for diagnostics
        try:
            err_path = Path.home() / ".cache" / "kyth" / "kyth-welcome-errors.log"
            err_path.parent.mkdir(parents=True, exist_ok=True)
            with err_path.open("a", encoding="utf-8") as fh:
                fh.write(f"[{exc_type.__name__}] {exc_value}\n")
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            pass
    sys.excepthook = _log_uncaught

    app = QApplication(sys.argv)
    # Join background probe threads before Qt tears down: destroying a running
    # QThread aborts the process, turning a normal quit into a crash.
    app.aboutToQuit.connect(shutdown_threads)
    app.setApplicationName("kyth-welcome")
    app.setDesktopFileName("kyth-welcome")
    app.setWindowIcon(QIcon.fromTheme("kyth"))
    app.setStyleSheet(QSS)

    # Lazy-import windows so `import kyth_welcome.app` stays cheap for probe/cache checks
    from .windows import MainWindow as _MainWindow
    from .wizard import WizardWindow as _WizardWindow

    if IS_LIVE:
        win = _MainWindow()
    elif is_first_run():
        win = _WizardWindow()
    else:
        win = _MainWindow()
    win.setWindowIcon(QIcon.fromTheme("kyth"))
    win.showMaximized()
    if start_page and isinstance(win, _MainWindow):
        win._navigate_to(start_page)
    remove_autostart()
    sys.exit(app.exec())
