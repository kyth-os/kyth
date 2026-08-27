"""Local HTTP transport for the web-based Hub shell (web_shell.py).

Same shape as kyth_installer/server.py — a plain http.server bound to
127.0.0.1 only, serving the built React app's static files — deliberately
not reusing that module directly since the installer's server carries
disk-partitioning routes and a session-token auth model this doesn't need
yet. Once real write endpoints land here (triggering a Guardian repair,
applying a scheduler change), they should get the same
requires_auth/requires_same_origin treatment installer's RouteSpec does —
this is read-only (static files, or a future GET-only JSON API) for now,
which is why that machinery isn't duplicated yet rather than being an
oversight.
"""
from __future__ import annotations

import logging
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_logger = logging.getLogger(__name__)

DEFAULT_PORT = 8642


class _Handler(BaseHTTPRequestHandler):
    server_version = "KythHubWeb/0.1"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A002 -- match BaseHTTPRequestHandler signature
        _logger.debug("web_server: " + fmt, *args)

    def _reject(self, code: int, message: str) -> None:
        body = message.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _same_origin(self) -> bool:
        # Bound to 127.0.0.1 only (see _Server below), so no remote host can
        # reach this at all; the Host header check is defense against
        # DNS-rebinding from a page loaded in a *different* local origin
        # (e.g. a browser tab) — same posture as kyth_installer/server.py.
        host = self.headers.get("Host", "")
        return host.split(":", 1)[0] in ("127.0.0.1", "localhost")

    def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler API
        if not self._same_origin():
            self._reject(403, "forbidden")
            return
        path = self.path.split("?", 1)[0]
        if path == "/":
            path = "/index.html"
        root: Path = self.server.static_root  # type: ignore[attr-defined]
        target = (root / path.lstrip("/")).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            self._reject(403, "forbidden")
            return
        if not target.is_file():
            # SPA client-side routing (HashRouter) — any missing static path
            # falls back to index.html rather than 404ing.
            target = root / "index.html"
        content_type, _ = mimetypes.guess_type(str(target))
        try:
            body = target.read_bytes()
        except OSError:
            self._reject(404, "not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _Server(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], static_root: Path):
        super().__init__(address, _Handler)
        self.static_root = static_root


class HubWebServer:
    """Background-thread static file server for the web Hub shell."""

    def __init__(self, static_root: Path, port: int = DEFAULT_PORT):
        self._static_root = static_root
        self._port = port
        self._httpd: _Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}/"

    def start(self) -> None:
        if self._httpd is not None:
            return
        self._httpd = _Server(("127.0.0.1", self._port), self._static_root)
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="kyth-hub-web", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None
        self._thread = None
