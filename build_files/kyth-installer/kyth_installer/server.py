"""Authenticated local HTTP transport for the installer application."""

import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import config
from .config import LOG_FILE, PORT, SESSION_TOKEN, SOURCE_IMAGE, _IS_LIVE_SESSION
from .context import InstallerContext
from .disk import list_disks, list_partitions, list_free_space
from .partition_ops import FILESYSTEM_OPTIONS, get_journal
from .post_routes import PostRouteService
from .system import list_timezones

_WEBUI_DIR = Path(__file__).parent / "webui"


@dataclass(frozen=True)
class RouteSpec:
    method: str
    path: str
    requires_auth: bool = True
    requires_same_origin: bool = False


ROUTES = {
    "index": RouteSpec("GET", "/", requires_auth=False),
    "config": RouteSpec("GET", "/api/config"),
    "disks": RouteSpec("GET", "/api/disks"),
    "partitions": RouteSpec("GET", "/api/partitions"),
    "free_space": RouteSpec("GET", "/api/free-space"),
    "stream": RouteSpec("GET", "/api/stream"),
    "log": RouteSpec("GET", "/api/log"),
    "timezones": RouteSpec("GET", "/api/timezones"),
    "start": RouteSpec("POST", "/api/start", requires_same_origin=True),
    "reboot": RouteSpec("POST", "/api/reboot", requires_same_origin=True),
    # Manual partition management
    "partition_pending": RouteSpec("GET", "/api/disk/pending"),
    "filesystems": RouteSpec("GET", "/api/disk/filesystems"),
    "new_table": RouteSpec("POST", "/api/disk/new-table", requires_same_origin=True),
    "create_partition": RouteSpec("POST", "/api/disk/create", requires_same_origin=True),
    "delete_partition": RouteSpec("POST", "/api/disk/delete", requires_same_origin=True),
    "resize_partition": RouteSpec("POST", "/api/disk/resize", requires_same_origin=True),
    "format_partition": RouteSpec("POST", "/api/disk/format", requires_same_origin=True),
    "set_mountpoint": RouteSpec("POST", "/api/disk/set-mountpoint", requires_same_origin=True),
    "commit_partitions": RouteSpec("POST", "/api/disk/commit", requires_same_origin=True),
    "rollback_partitions": RouteSpec("POST", "/api/disk/rollback", requires_same_origin=True),
}


# path -> (webui filename, content-type, whether to inject the session token)
_STATIC_TEXT_ASSETS: dict[str, tuple[str, str, bool]] = {
    "/style.css": ("style.css", "text/css; charset=utf-8", False),
    "/app.js": ("app.js", "application/javascript; charset=utf-8", True),
    "/state.js": ("state.js", "application/javascript; charset=utf-8", True),
}


def _read_webui(name: str) -> str:
    return (_WEBUI_DIR / name).read_text()


def _parse_cookie_header(cookie_header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    if not cookie_header:
        return cookies
    for pair in cookie_header.split(";"):
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def _route_for(method: str, path: str) -> RouteSpec | None:
    method = method.upper()
    for route in ROUTES.values():
        if route.method == method and route.path == path:
            return route
    return None


class Handler(BaseHTTPRequestHandler):
    @property
    def context(self) -> InstallerContext:
        context = getattr(getattr(self, "server", None), "context", None)
        if context is None:
            raise RuntimeError("Installer HTTP handler has no runtime context")
        return context

    def log_message(self, *_):
        pass

    def _require_auth(self) -> bool:
        # Check header
        if self.headers.get("X-Kyth-Session-Token", "") == SESSION_TOKEN:
            return True
        # Check cookie
        cookies = _parse_cookie_header(self.headers.get("Cookie", ""))
        if cookies.get("bootstrap_auth") == SESSION_TOKEN:
            return True
        self.send_error(403, "Forbidden")
        return False

    @staticmethod
    def _is_trusted_local_url(value: str) -> bool:
        try:
            p = urlparse(value)
            return p.scheme == "http" and p.hostname in ("127.0.0.1", "localhost") and p.port == PORT
        except Exception:
            return False

    def _require_same_origin_context(self) -> bool:
        # The server only binds to 127.0.0.1 so no remote host can reach it.
        # Checking the Host header is sufficient to prevent DNS-rebinding.
        host = (self.headers.get("Host", "") or "").strip().lower()
        if host not in (f"127.0.0.1:{PORT}", f"localhost:{PORT}"):
            self.send_error(403, "Forbidden")
            return False
        return True

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        route = _route_for("GET", path)
        if (route is None or route.requires_same_origin) and not self._require_same_origin_context():
            return

        qs = parse_qs(urlparse(self.path).query)

        if path == "/":
            self._serve_index(qs)
            return

        if path in _STATIC_TEXT_ASSETS:
            self._serve_static_asset(path)
            return

        if not self._require_auth():
            return

        self._dispatch_api_get(route, qs)

    def _bootstrap_authenticated(self, qs: dict[str, list[str]]) -> bool:
        cookies = _parse_cookie_header(self.headers.get("Cookie", ""))
        if cookies.get("bootstrap_auth") == SESSION_TOKEN:
            return True
        if qs.get("bootstrap_token") and config._bootstrap_token is not None:
            with config._bootstrap_lock:
                if config._bootstrap_token is not None and qs.get("bootstrap_token") == [config._bootstrap_token]:
                    config._bootstrap_token = None
                    return True
        return False

    def _serve_index(self, qs: dict[str, list[str]]) -> None:
        if not self._bootstrap_authenticated(qs):
            self.send_error(403, "Forbidden")
            return
        body = _read_webui("index.html").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Set-Cookie", f"bootstrap_auth={SESSION_TOKEN}; Path=/; HttpOnly; SameSite=Strict")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static_asset(self, path: str) -> None:
        if not self._require_auth():
            return
        filename, content_type, inject_token = _STATIC_TEXT_ASSETS[path]
        text = _read_webui(filename)
        if inject_token:
            text = text.replace("SESSION_TOKEN_PLACEHOLDER", SESSION_TOKEN)
        self._send_text(text, content_type)

    def _dispatch_api_get(self, route: RouteSpec | None, qs: dict[str, list[str]]) -> None:
        if route == ROUTES["config"]:
            self._json({"source_image": SOURCE_IMAGE, "is_live": _IS_LIVE_SESSION})
        elif route == ROUTES["disks"]:
            self._json(list_disks())
        elif route == ROUTES["timezones"]:
            self._json(list_timezones())
        elif route == ROUTES["partitions"]:
            disk = (qs.get("disk") or [""])[0]
            self._json(list_partitions(disk) if disk else [])
        elif route == ROUTES["free_space"]:
            disk = (qs.get("disk") or [""])[0]
            self._json(list_free_space(disk) if disk else [])
        elif route == ROUTES["partition_pending"]:
            journal = get_journal(self.context)
            self._json(journal.pending() if journal else [])
        elif route == ROUTES["filesystems"]:
            self._json(FILESYSTEM_OPTIONS)
        elif route == ROUTES["stream"]:
            self._sse()
        elif route == ROUTES["log"]:
            self._serve_log()
        else:
            self.send_error(404)

    def _serve_log(self) -> None:
        try:
            text = LOG_FILE.read_text(errors="replace")
        except Exception as exc:
            text = f"Could not read installer log: {exc}\n"
        self._send_text(text, "text/plain; charset=utf-8")

    def _send_text(self, text: str, content_type: str) -> None:
        body = text.encode()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path
        route = _route_for("POST", path)
        if not self._require_auth():
            return
        if not self._require_same_origin_context():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode() or "{}")
        except Exception:
            self.send_error(400, "Invalid JSON")
            return

        route_name = next((name for name, spec in ROUTES.items() if spec is route), "")
        response = PostRouteService(self.context).dispatch(route_name, body)
        self._json(response.payload, status=response.status)
        return

    def _json(self, data: object, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        sent = 0
        while True:
            with self.context.events.condition:
                while sent >= len(self.context.events.events):
                    self.context.events.condition.wait(timeout=15)
                    if sent >= len(self.context.events.events):
                        try:
                            self.wfile.write(b":ka\n\n")
                            self.wfile.flush()
                        except Exception:
                            return
                batch = self.context.events.events[sent:]
            for event in batch:
                try:
                    self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                    self.wfile.flush()
                except Exception:
                    return
                sent += 1
                if event["type"] in ("done", "error"):
                    return


class _Server(ThreadingHTTPServer):
    # Allow the port to be reused immediately if the previous process crashed
    # and left a TIME_WAIT socket — prevents EADDRINUSE on rapid restarts.
    allow_reuse_address = True

    def __init__(self, server_address, handler_class, context: InstallerContext | None = None):
        self.context = context or InstallerContext()
        super().__init__(server_address, handler_class)
