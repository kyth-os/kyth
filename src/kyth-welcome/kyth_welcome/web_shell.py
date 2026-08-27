"""Native shell for the web-based Hub rewrite (kyth-hub-web/) — a
QWebEngineView window instead of the QWidget tree windows.py builds.

This is the thing being "nailed down" before any more pages get built in
React: can the web app live in a real native window with the same
integration points the current Hub has (single instance, --page deep
links), not just run in a browser tab. Answer here is yes — everything
below is real, not a sketch:

- QWebEngineView is already production code in this app (see
  page_vpn_saml_dialog.py's SamlBrowserDialog) — this isn't a new
  dependency, just a new use of one already shipping.
- Single-instance + --page deep-linking reuses instance_ipc.py exactly as
  app.py does; only "how do I tell the already-open window to navigate"
  changes, from a Python method call to a JS one
  (`window.location.hash = ...`, since the React app is HashRouter-based
  — see kyth-hub-web/src/main.tsx).

Deliberately a SEPARATE socket name / lock path from the production Hub
(app.py's kyth-welcome-<uid>) so this can run side by side with it during
development without either one forwarding launches to the other. Once/if
this shell replaces MainWindow, app.py's own constants are what a real
cutover would use.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .core_base import prefer_xwayland_if_wayland_plugin_missing, wait_for_display_setup
from .instance_ipc import (
    decode_activate_message,
    encode_activate_message,
    instance_server_window,
    retarget_instance_server,
)
from .qt import QApplication, QLocalServer, QLocalSocket, QUrl, QWebEngineView, _WEBENGINE_AVAILABLE
from .services.web_server import HubWebServer

_SOCKET_NAME_PREFIX = "kyth-welcome-web-preview"


def _instance_socket_name() -> str:
    return f"{_SOCKET_NAME_PREFIX}-{os.getuid()}"


def _forward_to_running_instance(page: str | None) -> bool:
    probe = QLocalSocket()
    probe.connectToServer(_instance_socket_name())
    if not probe.waitForConnected(500):
        return False
    probe.write(encode_activate_message(page))
    probe.waitForBytesWritten(500)
    probe.disconnectFromServer()
    return True


class HubWebWindow:
    """Thin wrapper, not a QMainWindow subclass — everything the current
    Hub gets from being a real QWidget tree (menus, tray integration,
    theming via QSS) the web app now owns instead; this just hosts it."""

    def __init__(self, server_url: str):
        from .qt import QMainWindow

        self._server_url = server_url
        self.window = QMainWindow()
        self.window.setWindowTitle("Kyth Hub")
        self.window.resize(1440, 900)
        self.view = QWebEngineView()
        self.view.setUrl(QUrl(server_url))
        self.window.setCentralWidget(self.view)

    def show(self) -> None:
        self.window.show()

    def showMaximized(self) -> None:  # noqa: N802 -- mirrors QMainWindow API used by app.py
        self.window.showMaximized()

    def raise_(self) -> None:
        self.window.raise_()

    def activateWindow(self) -> None:  # noqa: N802
        self.window.activateWindow()

    def _navigate_to(self, page: str) -> None:
        # HashRouter, not history-API routing (see main.tsx) — the React
        # side reads location.hash, so this is the entire "deep link"
        # contract between the two languages: one string, one convention.
        route = _ROUTE_FOR_PAGE.get(page, "/")
        self.view.page().runJavaScript(f"window.location.hash = {json.dumps(route)};")


# Page-key -> route mapping — placeholder until the real page_registry.py
# key set has a web route for every entry. Kept as an explicit table
# rather than a lowercase-and-slugify transform so a page without a web
# route yet (everything except Home right now) fails obviously (falls
# back to "/") instead of guessing a URL that 404s inside the SPA.
_ROUTE_FOR_PAGE = {
    "Welcome": "/",
    "Play": "/play",
    "Apps": "/apps",
    "This PC": "/this-pc",
    "Move In": "/move-in",
}


def _start_instance_server(window: HubWebWindow) -> QLocalServer | None:
    server = QLocalServer()
    server.removeServer(_instance_socket_name())
    if not server.listen(_instance_socket_name()):
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
            if page:
                win._navigate_to(page)
        connection.close()

    server.newConnection.connect(handle_new_connection)
    return server


def _static_root() -> Path:
    # Dev: the Vite build output checked into kyth-hub-web/dist. Once this
    # ships, the built assets move to package-data next to kyth_welcome
    # (see kyth-installer's pyproject.toml package-data pattern) and this
    # becomes an installed path instead of a source-tree-relative one.
    override = os.environ.get("KYTH_HUB_WEB_DIST")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "kyth-hub-web" / "dist"


def main() -> None:
    if not _WEBENGINE_AVAILABLE:
        print("QtWebEngine is not available — cannot run the web Hub shell.", file=sys.stderr)
        sys.exit(1)

    static_root = _static_root()
    if not (static_root / "index.html").is_file():
        print(f"No build found at {static_root} — run: cd src/kyth-hub-web && npm run build", file=sys.stderr)
        sys.exit(1)

    start_page = None
    raw_args = sys.argv[1:]
    for i, a in enumerate(raw_args):
        if a == "--page" and i + 1 < len(raw_args):
            start_page = raw_args[i + 1]

    wait_for_display_setup()
    prefer_xwayland_if_wayland_plugin_missing()

    app = QApplication(sys.argv)
    app.setApplicationName("kyth-welcome-web-preview")
    app.setApplicationDisplayName("Kyth Hub (web preview)")

    if _forward_to_running_instance(start_page):
        return

    server_process = HubWebServer(static_root)
    server_process.start()
    app.aboutToQuit.connect(server_process.stop)

    win = HubWebWindow(server_process.url)
    instance_server = _start_instance_server(win)
    if instance_server is None:
        if _forward_to_running_instance(start_page):
            return
        print("Kyth Hub (web preview) is already running", file=sys.stderr)
        return
    app._hub_instance_server = instance_server  # type: ignore[attr-defined]

    win.showMaximized()
    if start_page:
        win._navigate_to(start_page)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
