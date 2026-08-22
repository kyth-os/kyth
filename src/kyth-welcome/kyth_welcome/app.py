import os
import sys
import traceback
from pathlib import Path

# __KYTH_GENERATED_IMPORTS__
from .core_base import IS_LIVE, is_first_run, prefer_xwayland_if_wayland_plugin_missing, remove_autostart, wait_for_display_setup
from .instance_ipc import (
    decode_activate_message,
    encode_activate_message,
    instance_server_window,
    retarget_instance_server,
)
from .services.runtime import shutdown_threads
from kyth_shared.session import acquire_run_lock
from .qt import (
    QApplication, QIcon, QLocalServer, QLocalSocket,
)
from .theme import (
    QSS,
)
from .windows import MainWindow
from .wizard import WizardWindow

_SOCKET_NAME_PREFIX = "kyth-welcome"


def _instance_socket_name() -> str:
    return f"{_SOCKET_NAME_PREFIX}-{os.getuid()}"


def _instance_lock_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    if runtime:
        return Path(runtime) / "kyth-welcome.instance.lock"
    return Path.home() / ".cache" / "kyth" / "kyth-welcome.instance.lock"


def _forward_to_running_instance(page: str | None) -> bool:
    """If another Hub owns the local socket, ask it to raise (and optionally navigate)."""
    socket_name = _instance_socket_name()
    probe = QLocalSocket()
    probe.connectToServer(socket_name)
    if not probe.waitForConnected(500):
        return False
    probe.write(encode_activate_message(page))
    probe.waitForBytesWritten(500)
    probe.disconnectFromServer()
    return True


def _start_instance_server(window: MainWindow | WizardWindow) -> QLocalServer | None:
    """Listen for second-launch activate messages; return None if we lost the race.

    The activate handler reads ``server._hub_window`` so wizard → Hub handoff
    can retarget the socket without constructing a second listener.
    """
    socket_name = _instance_socket_name()
    server = QLocalServer()
    server.removeServer(socket_name)
    if not server.listen(socket_name):
        return None
    retarget_instance_server(server, window)

    def handle_new_connection() -> None:
        connection = server.nextPendingConnection()
        if connection is None:
            return
        win = instance_server_window(server)
        if connection.waitForReadyRead(500) and win is not None:
            page = decode_activate_message(bytes(connection.readAll()))
            win.show()
            win.raise_()
            win.activateWindow()
            if page and hasattr(win, "_navigate_to"):
                win._navigate_to(page)
        connection.close()

    server.newConnection.connect(handle_new_connection)
    return server


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
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
        except Exception:
            pass
        # Also append a concise marker to the cache error file for diagnostics
        try:
            err_path = Path.home() / ".cache" / "kyth" / "kyth-welcome-errors.log"
            err_path.parent.mkdir(parents=True, exist_ok=True)
            with err_path.open("a", encoding="utf-8") as fh:
                fh.write(f"[{exc_type.__name__}] {exc_value}\n")
        except Exception:
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

    # Single-instance: forward to the running Hub (raise + optional --page) instead
    # of the old check-then-write PID lock race that allowed dual Hubs.
    if _forward_to_running_instance(start_page):
        return

    # Hold a run lock *before* constructing a window so a lost listen race
    # cannot still show a second Hub. Fail closed if we cannot own the lock
    # and cannot forward to the winner.
    lock = acquire_run_lock(_instance_lock_path())
    if lock is None:
        if _forward_to_running_instance(start_page):
            return
        print("System Hub is already running", file=sys.stderr)
        return

    try:
        if IS_LIVE:
            win = MainWindow()
        elif is_first_run():
            win = WizardWindow()
        else:
            win = MainWindow()

        server = _start_instance_server(win)
        if server is None:
            if _forward_to_running_instance(start_page):
                return
            print("System Hub is already running", file=sys.stderr)
            return
        app._hub_instance_server = server  # type: ignore[attr-defined]
        app._hub_instance_lock = lock  # type: ignore[attr-defined]
        lock = None  # held for process lifetime via the QApplication attr

        win.setWindowIcon(QIcon.fromTheme("kyth"))
        win.showMaximized()
        if start_page and isinstance(win, MainWindow):
            win._navigate_to(start_page)
        remove_autostart()
        sys.exit(app.exec())
    finally:
        if lock is not None:
            try:
                lock.close()
            except OSError:
                pass
