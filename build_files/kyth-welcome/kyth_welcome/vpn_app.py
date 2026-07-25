"""Dedicated VPN window backed by System Hub's single VPN page."""

from __future__ import annotations

import os
import sys
import traceback

from .core_base import (
    _prefer_xwayland_if_wayland_plugin_missing,
    _shutdown_threads,
    _wait_for_display_setup,
)
from .page_vpn import VpnPage
from .qt import QApplication, QIcon, QLocalServer, QLocalSocket, QMainWindow
from .theme import QSS


class VpnWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VPN Connect")
        self.setWindowIcon(QIcon.fromTheme("network-vpn"))
        self.setMinimumSize(760, 680)
        self.vpn_page = VpnPage()
        self.setCentralWidget(self.vpn_page)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        worker = self.vpn_page._worker
        if worker is not None and worker.isRunning():
            self.hide()
            event.ignore()
            return
        event.accept()


def main() -> None:
    _wait_for_display_setup()
    _prefer_xwayland_if_wayland_plugin_missing()

    def log_uncaught(exc_type, exc_value, exc_tb):
        traceback.print_exception(exc_type, exc_value, exc_tb, file=sys.stderr)

    sys.excepthook = log_uncaught
    app = QApplication(sys.argv)
    app.aboutToQuit.connect(_shutdown_threads)
    app.setApplicationName("kyth-vpn-connect")
    app.setDesktopFileName("kyth-vpn-connect")
    app.setWindowIcon(QIcon.fromTheme("network-vpn"))
    app.setStyleSheet(QSS)

    socket_name = f"kyth-vpn-connect-{os.getuid()}"
    probe = QLocalSocket()
    probe.connectToServer(socket_name)
    if probe.waitForConnected(500):
        probe.write(b"show")
        probe.waitForBytesWritten(500)
        return

    server = QLocalServer()
    server.removeServer(socket_name)
    if not server.listen(socket_name):
        print(f"Warning: could not start VPN single-instance listener: {server.errorString()}")

    window = VpnWindow()

    def handle_new_connection() -> None:
        connection = server.nextPendingConnection()
        if connection and connection.waitForReadyRead(500):
            message = bytes(connection.readAll()).decode("utf-8", errors="replace")
            if message == "show":
                window.show()
                window.raise_()
                window.activateWindow()
        if connection:
            connection.close()

    server.newConnection.connect(handle_new_connection)
    app._vpn_instance_server = server  # type: ignore[attr-defined]
    window.show()
    sys.exit(app.exec())
