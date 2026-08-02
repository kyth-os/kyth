"""Behavioral tests for server.py's do_GET path: bootstrap/session auth,
static asset serving, and API route dispatch. server.py had no dedicated GET
tests before this — do_POST already had coverage via
InstallerServerConfirmationTests in test_kyth_installer_storage.py, so this
file follows the same Handler.__new__() construction pattern for GET.
"""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files/kyth-installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from kyth_installer import config, server  # noqa: E402
from kyth_installer.context import InstallerContext  # noqa: E402


def _make_handler(path: str, *, host: str | None = None, cookie: str = "") -> server.Handler:
    handler = server.Handler.__new__(server.Handler)
    headers = {"Cookie": cookie}
    if host is not None:
        headers["Host"] = host
    handler.headers = headers
    handler.rfile = io.BytesIO(b"")
    handler.wfile = io.BytesIO()
    handler.path = path
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.send_error = MagicMock()
    handler.server = SimpleNamespace(context=InstallerContext())
    return handler


class ParseCookieAndRouteTests(unittest.TestCase):
    def test_parse_cookie_header_handles_blank_and_malformed_pairs(self):
        cookies = server._parse_cookie_header("a=1; no-value; b = two ")
        self.assertEqual(cookies, {"a": "1", "b": "two"})
        self.assertEqual(server._parse_cookie_header(""), {})


class ServerIndexTests(unittest.TestCase):
    """"/" is the only route with its own bootstrap-token auth path (cookie
    or one-shot query token) instead of the shared session-token auth used
    by every other route."""

    def setUp(self):
        config._bootstrap_token = None

    def tearDown(self):
        config._bootstrap_token = None

    def test_index_rejects_without_any_auth(self):
        handler = _make_handler("/", host=f"127.0.0.1:{config.PORT}")
        handler.do_GET()
        handler.send_error.assert_called_once_with(403, "Forbidden")
        self.assertEqual(handler.wfile.getvalue(), b"")

    def test_index_accepts_valid_bootstrap_cookie(self):
        handler = _make_handler(
            "/", host=f"127.0.0.1:{config.PORT}",
            cookie=f"bootstrap_auth={config.SESSION_TOKEN}",
        )
        handler.do_GET()
        handler.send_error.assert_not_called()
        handler.send_response.assert_called_once_with(200)
        self.assertIn(b"<", handler.wfile.getvalue())
        set_cookie_calls = [c for c in handler.send_header.call_args_list if c.args[0] == "Set-Cookie"]
        self.assertTrue(set_cookie_calls)
        self.assertIn(config.SESSION_TOKEN, set_cookie_calls[0].args[1])

    def test_index_consumes_one_shot_bootstrap_token_from_query_string(self):
        config._bootstrap_token = "one-shot-token"
        handler = _make_handler(
            "/?bootstrap_token=one-shot-token", host=f"127.0.0.1:{config.PORT}",
        )
        handler.do_GET()
        handler.send_error.assert_not_called()
        handler.send_response.assert_called_once_with(200)
        # The token is single-use: a second request with the same query
        # token (and no cookie yet) must be rejected.
        self.assertIsNone(config._bootstrap_token)
        second = _make_handler(
            "/?bootstrap_token=one-shot-token", host=f"127.0.0.1:{config.PORT}",
        )
        second.do_GET()
        second.send_error.assert_called_once_with(403, "Forbidden")

    def test_index_requires_same_origin_host_header(self):
        handler = _make_handler("/", host="evil.example:1234")
        handler.do_GET()
        handler.send_error.assert_called_once_with(403, "Forbidden")


class ServerStaticAssetTests(unittest.TestCase):
    def test_style_css_requires_session_auth(self):
        handler = _make_handler("/style.css", host=f"127.0.0.1:{config.PORT}")
        handler.do_GET()
        handler.send_error.assert_called_once_with(403, "Forbidden")

    def test_style_css_served_when_authenticated(self):
        handler = _make_handler(
            "/style.css", host=f"127.0.0.1:{config.PORT}",
        )
        handler.headers["X-Kyth-Session-Token"] = config.SESSION_TOKEN
        handler.do_GET()
        handler.send_error.assert_not_called()
        handler.send_response.assert_called_once_with(200)
        content_type_calls = [c for c in handler.send_header.call_args_list if c.args[0] == "Content-Type"]
        self.assertIn("text/css", content_type_calls[0].args[1])
        self.assertIn(b"{", handler.wfile.getvalue())

    def test_app_js_has_session_token_placeholder_replaced(self):
        handler = _make_handler("/app.js", host=f"127.0.0.1:{config.PORT}")
        handler.headers["X-Kyth-Session-Token"] = config.SESSION_TOKEN
        handler.do_GET()
        handler.send_error.assert_not_called()
        body = handler.wfile.getvalue().decode()
        self.assertNotIn("SESSION_TOKEN_PLACEHOLDER", body)
        self.assertIn(config.SESSION_TOKEN, body)


class ServerApiDispatchTests(unittest.TestCase):
    def _handler(self, path: str) -> server.Handler:
        handler = _make_handler(path, host=f"127.0.0.1:{config.PORT}")
        handler.headers["X-Kyth-Session-Token"] = config.SESSION_TOKEN
        return handler

    def _json_body(self, handler) -> object:
        return json.loads(handler.wfile.getvalue().decode())

    def test_config_route_reports_source_image_and_live_flag(self):
        handler = self._handler("/api/config")
        handler.do_GET()
        payload = self._json_body(handler)
        self.assertEqual(payload["source_image"], config.SOURCE_IMAGE)
        self.assertIn("is_live", payload)
        self.assertIn("source", payload)

    def test_disks_route_delegates_to_list_disks(self):
        handler = self._handler("/api/disks")
        with patch.object(server, "list_disks", return_value=[{"name": "/dev/sda"}]):
            handler.do_GET()
        self.assertEqual(self._json_body(handler), [{"name": "/dev/sda"}])

    def test_partitions_route_requires_disk_query_param(self):
        handler = self._handler("/api/partitions")
        handler.do_GET()
        self.assertEqual(self._json_body(handler), [])

    def test_partitions_route_delegates_with_disk_param(self):
        handler = self._handler("/api/partitions?disk=%2Fdev%2Fsda")
        with patch.object(server, "list_partitions", return_value=[{"name": "/dev/sda1"}]) as mock_lp:
            handler.do_GET()
        mock_lp.assert_called_once_with("/dev/sda")
        self.assertEqual(self._json_body(handler), [{"name": "/dev/sda1"}])

    def test_free_space_route_delegates_with_disk_param(self):
        handler = self._handler("/api/free-space?disk=%2Fdev%2Fsda")
        with patch.object(server, "list_free_space", return_value=[{"start_bytes": 0}]) as mock_lfs:
            handler.do_GET()
        mock_lfs.assert_called_once_with("/dev/sda")
        self.assertEqual(self._json_body(handler), [{"start_bytes": 0}])

    def test_partition_pending_route_returns_empty_without_a_journal(self):
        handler = self._handler("/api/disk/pending")
        handler.do_GET()
        self.assertEqual(self._json_body(handler), [])

    def test_filesystems_route_returns_filesystem_options(self):
        handler = self._handler("/api/disk/filesystems")
        handler.do_GET()
        payload = self._json_body(handler)
        self.assertTrue(any(item.get("id") == "btrfs" for item in payload))

    def test_log_route_returns_log_text(self):
        handler = self._handler("/api/log")
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "installer.log"
            log_path.write_text("install log contents")
            with patch.object(server, "LOG_FILE", log_path):
                handler.do_GET()
        self.assertEqual(handler.wfile.getvalue(), b"install log contents")

    def test_log_route_reports_read_failure_instead_of_raising(self):
        handler = self._handler("/api/log")
        with patch.object(server, "LOG_FILE", Path("/nonexistent/kyth-installer.log")):
            handler.do_GET()
        self.assertIn(b"Could not read installer log", handler.wfile.getvalue())

    def test_report_route_returns_transaction_json(self):
        handler = self._handler("/api/report")
        with patch.object(server, "read_transaction_state", return_value={"status": "complete"}):
            handler.do_GET()
        self.assertEqual(self._json_body(handler), {"status": "complete"})

    def test_unknown_route_is_404(self):
        handler = self._handler("/api/does-not-exist")
        handler.do_GET()
        handler.send_error.assert_called_once_with(404)

    def test_api_route_requires_session_auth(self):
        handler = _make_handler("/api/disks", host=f"127.0.0.1:{config.PORT}")
        handler.do_GET()
        handler.send_error.assert_called_once_with(403, "Forbidden")


class ServerSseTests(unittest.TestCase):
    def test_stream_route_replays_buffered_events_and_stops_on_done(self):
        handler = _make_handler(
            "/api/stream", host=f"127.0.0.1:{config.PORT}",
        )
        handler.headers["X-Kyth-Session-Token"] = config.SESSION_TOKEN
        handler.server.context.events.publish({"type": "log", "text": "hello"})
        handler.server.context.events.publish({"type": "done"})
        handler.do_GET()
        body = handler.wfile.getvalue().decode()
        self.assertIn("id: 0", body)
        self.assertIn('"text": "hello"', body)
        self.assertIn('"type": "done"', body)

    def test_stream_resumes_after_last_event_id(self):
        handler = _make_handler("/api/stream", host=f"127.0.0.1:{config.PORT}")
        handler.headers["X-Kyth-Session-Token"] = config.SESSION_TOKEN
        handler.headers["Last-Event-ID"] = "0"
        handler.server.context.events.publish({"type": "log", "text": "old"})
        handler.server.context.events.publish({"type": "done"})
        handler.do_GET()
        body = handler.wfile.getvalue().decode()
        self.assertNotIn("old", body)
        self.assertIn("id: 1", body)


class ServerConstructionTests(unittest.TestCase):
    def test_server_defaults_to_a_fresh_context_when_none_given(self):
        srv = server._Server(("127.0.0.1", 0), server.Handler)
        try:
            self.assertIsInstance(srv.context, InstallerContext)
        finally:
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
