"""HubWebServer (services/web_server.py) — the local static file server
behind the web Hub shell prototype (web_shell.py). Covers the two things
that matter for a server bound to 127.0.0.1 and serving a SPA: it can't be
tricked into reading outside its static root, and a missing path falls
back to index.html (HashRouter client-side routing) rather than 404ing.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services.web_server import HubWebServer  # noqa: E402


class HubWebServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "index.html").write_text("<title>Kyth Hub</title><div id=root></div>", encoding="utf-8")
        (root / "style.css").write_text("body{color:red}", encoding="utf-8")
        secret_dir = root.parent / "kyth-web-server-test-secret"
        secret_dir.mkdir(exist_ok=True)
        (secret_dir / "outside.txt").write_text("should never be served", encoding="utf-8")
        cls.secret_dir = secret_dir

        cls.server = HubWebServer(root, port=0)
        # port=0 asks the OS for a free port; read back what it actually bound.
        cls.server.start()
        cls.port = cls.server._httpd.server_address[1]  # type: ignore[union-attr]

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.stop()
        except Exception:
            pass
        try:
            cls.tmp.cleanup()
        except Exception:
            pass
        try:
            sd = getattr(cls, "secret_dir", None)
            if sd is not None and sd.exists():
                for f in sd.glob("*"):
                    try:
                        f.unlink()
                    except FileNotFoundError:
                        pass
                try:
                    sd.rmdir()
                except FileNotFoundError:
                    pass
                except OSError:
                    import shutil
                    try:
                        shutil.rmtree(sd, ignore_errors=True)
                    except Exception:
                        pass
        except Exception:
            pass

    def _get(self, path: str, host: str = "127.0.0.1") -> tuple[int, bytes]:
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers={"Host": host})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_serves_index_at_root(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Kyth Hub", body)

    def test_serves_a_real_static_file_with_content_type(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/style.css")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/css", resp.headers.get("Content-Type", ""))

    def test_missing_path_falls_back_to_index_for_spa_routing(self):
        status, body = self._get("/this-pc/anything")
        self.assertEqual(status, 200)
        self.assertIn(b"Kyth Hub", body)

    def test_path_traversal_is_blocked_not_served_from_outside_root(self):
        status, body = self._get("/../kyth-web-server-test-secret/outside.txt")
        # Never 200 with the secret content, whatever status urllib settles
        # on after its own path normalization.
        self.assertNotIn(b"should never be served", body)
        self.assertIn(status, (200, 403, 404))
        if status == 200:
            # Normalized to a real in-root path (index.html) — fine — but
            # must not be the secret file's content.
            self.assertIn(b"Kyth Hub", body)

    def test_wrong_host_header_is_rejected(self):
        status, _ = self._get("/", host="evil.example.com")
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
