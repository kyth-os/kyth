"""HTTP server: cookie/route helpers, the request Handler, and the
ThreadingHTTPServer subclass that main() binds to 127.0.0.1.

Reaches into install.py's mutable run state and config.py's bootstrap
token module-qualified (install._state, config._bootstrap_token) rather
than importing those names directly, since direct import would bind a
snapshot that later mutations in those modules would not update.
"""

import json
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import config, install
from .config import LOG_FILE, PORT, SESSION_TOKEN, SOURCE_IMAGE, _IS_LIVE_SESSION
from .disk import _safe_int, find_efi_partition, list_disks, list_partitions, list_free_space
from .plan import ROUTES, RouteSpec, _validate_storage_intent
from .system import _as_root, _hash_password, list_timezones

_WEBUI_DIR = Path(__file__).parent / "webui"


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
    def log_message(self, *_):
        pass

    def _require_auth(self) -> bool:
        # Check header
        if self.headers.get("X-Kyth-Session-Token", "") == SESSION_TOKEN:
            return True
        # Check cookie
        cookie_header = self.headers.get("Cookie", "")
        if cookie_header:
            for pair in cookie_header.split(";"):
                if "=" in pair:
                    k, v = pair.strip().split("=", 1)
                    if k == "bootstrap_auth" and v == SESSION_TOKEN:
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

        query = urlparse(self.path).query
        from urllib.parse import parse_qs
        qs = parse_qs(query)

        cookies = _parse_cookie_header(self.headers.get("Cookie", ""))

        is_authenticated = False

        if cookies.get("bootstrap_auth") == SESSION_TOKEN:
            is_authenticated = True
        elif qs.get("bootstrap_token") and config._bootstrap_token is not None:
            with config._bootstrap_lock:
                if config._bootstrap_token is not None and qs.get("bootstrap_token") == [config._bootstrap_token]:
                    is_authenticated = True
                    config._bootstrap_token = None

        if path == "/":
            if not is_authenticated:
                self.send_error(403, "Forbidden")
                return

            injected_html = _read_webui("index.html")
            body = injected_html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.send_header("Set-Cookie", f"bootstrap_auth={SESSION_TOKEN}; Path=/; HttpOnly; SameSite=Strict")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/style.css":
            if not self._require_auth():
                return
            body = _read_webui("style.css").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/app.js":
            if not self._require_auth():
                return
            body = _read_webui("app.js").replace("SESSION_TOKEN_PLACEHOLDER", SESSION_TOKEN).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
            return

        # Authenticate all other API endpoints
        if not self._require_auth():
            return

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
        elif route == ROUTES["stream"]:
            self._sse()
        elif route == ROUTES["log"]:
            try:
                text = LOG_FILE.read_text(errors="replace")
            except Exception as exc:
                text = f"Could not read installer log: {exc}\n"
            body = text.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

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

        if route == ROUTES["start"]:
            disk = body.get("disk", "")
            disks = {d["name"]: d for d in list_disks()}
            if disk not in disks:
                self.send_error(400, "Invalid disk")
                return

            install_mode = body.get("install_mode", "wipe")
            if install_mode not in ("wipe", "alongside", "resize_ntfs", "free_space"):
                install_mode = "wipe"

            target_partition = ""
            resize_partition = ""
            resize_gib = 0
            efi_partition = ""
            free_region_start = 0
            free_region_end = 0
            if install_mode == "alongside":
                target_partition = body.get("target_partition", "")
                partitions = {p.get("name"): p for p in list_partitions(disk)}
                if target_partition not in partitions:
                    self.send_error(400, "Invalid target partition")
                    return
                efi_partition = body.get("efi_partition", "") or find_efi_partition(disk)
            elif install_mode == "resize_ntfs":
                resize_partition = body.get("resize_partition") or body.get("target_partition", "")
                resize_gib = _safe_int(body.get("resize_gib") or body.get("shrink_gib") or 0)
                partitions = {p.get("name"): p for p in list_partitions(disk)}
                if resize_partition not in partitions or resize_gib < 32:
                    self._json({"started": False, "message": "Invalid NTFS resize target."}, status=400)
                    return
                efi_partition = body.get("efi_partition", "") or find_efi_partition(disk)
            elif install_mode == "free_space":
                free_region_start = _safe_int(body.get("free_region_start"), -1)
                free_region_end = _safe_int(body.get("free_region_end"), -1)
                regions = list_free_space(disk)
                if free_region_start < 0 or free_region_end <= free_region_start or not any(
                    r["start_bytes"] <= free_region_start and r["end_bytes"] >= free_region_end for r in regions
                ):
                    self._json({"started": False, "message": "Invalid free space region."}, status=400)
                    return
                efi_partition = body.get("efi_partition", "") or find_efi_partition(disk)
            elif disks[disk].get("current") and not _IS_LIVE_SESSION:
                self._json({
                    "started": False,
                    "message": (
                        "This is the disk running the current KythOS session.\n\n"
                        "The running root filesystem cannot be unmounted, so reinstalling "
                        "to this disk is only supported from the live ISO."
                    ),
                }, status=409)
                return

            validation_state = {
                "disk": disk,
                "install_mode": install_mode,
                "target_partition": target_partition,
                "resize_partition": resize_partition,
                "resize_gib": resize_gib,
                "free_region_start": free_region_start,
                "free_region_end": free_region_end,
            }
            try:
                _validate_storage_intent(validation_state)
            except RuntimeError as exc:
                self._json({"started": False, "message": str(exc)}, status=409)
                return

            # The UI only lets the "Install Now" button enable once these
            # boxes are checked; re-check server-side so a stale/bypassed
            # frontend can't skip the user's explicit destructive-action ack.
            is_current_disk = bool(disks[disk].get("current"))
            current_ok = install_mode == "alongside" or not is_current_disk or bool(body.get("confirm_current"))
            if not (body.get("confirm_backup") and body.get("confirm_erase") and current_ok):
                self._json({
                    "started": False,
                    "message": "Please confirm the on-screen acknowledgements before starting the install.",
                }, status=400)
                return

            password = body.get("password", "")
            try:
                password_hash = _hash_password(password)
            except Exception as exc:
                self._json({"started": False, "message": f"Could not hash password: {exc}"}, status=500)
                return

            timezone = body.get("timezone", "UTC") or "UTC"
            if timezone not in set(list_timezones()):
                timezone = "UTC"
            username = body.get("username", "")
            if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,30}", username):
                self.send_error(400, "Invalid username")
                return
            hostname = body.get("hostname", "kyth")
            if not re.fullmatch(r"[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?", hostname):
                self.send_error(400, "Invalid hostname")
                return
            kernel = body.get("kernel", "fedora") or "fedora"
            mok_password = body.get("mok_password", "") or ""

            if not install._install_lock.acquire(blocking=False):
                self._json({"started": False, "message": "An installation is already running."}, status=409)
                return
            install._state.update({
                "disk": disk,
                "install_mode": install_mode,
                "target_partition": target_partition,
                "resize_partition": resize_partition,
                "resize_gib": resize_gib,
                "free_region_start": free_region_start,
                "free_region_end": free_region_end,
                "efi_partition": efi_partition,
                "hostname": hostname,
                "timezone": timezone,
                "username": username,
                "password_hash": password_hash,
                "kernel": kernel,
                "mok_password": mok_password,
            })

            def _worker():
                try:
                    install._run_install()
                finally:
                    install._install_lock.release()

            threading.Thread(target=_worker, daemon=True).start()
            self._json({"started": True})
            return

        if route == ROUTES["reboot"]:
            result = subprocess.run(
                _as_root(["systemctl", "reboot"]),
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                self._json({"ok": False, "error": result.stderr.strip() or "reboot command failed"}, status=500)
                return
            self._json({"ok": True})
            return

        self.send_error(404)

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
            with install._new_event:
                while sent >= len(install._events):
                    install._new_event.wait(timeout=15)
                    if sent >= len(install._events):
                        try:
                            self.wfile.write(b":ka\n\n")
                            self.wfile.flush()
                        except Exception:
                            return
                batch = install._events[sent:]
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

