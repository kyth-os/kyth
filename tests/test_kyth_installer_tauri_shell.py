"""Contracts for the Phase 2 React/Tauri installer shell."""
from __future__ import annotations

import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
INSTALLER_WEB = ROOT / "src/kyth-installer-web"
SHELL_RS = INSTALLER_WEB / "src-tauri/src/main.rs"
LAUNCHER = ROOT / "src/kyth-installer/kyth_installer/app.py"
SERVER = ROOT / "src/kyth-installer/kyth_installer/server.py"


class InstallerTauriShellTests(unittest.TestCase):
    def test_shell_embeds_assets_and_has_no_privileged_bridge(self):
        config = json.loads((INSTALLER_WEB / "src-tauri/tauri.conf.json").read_text())
        self.assertEqual(config["build"]["frontendDist"], "../dist")
        self.assertIn("127.0.0.1:7777", config["app"]["security"]["csp"])
        rust = SHELL_RS.read_text()
        self.assertIn('const BACKEND_URL: &str = "http://127.0.0.1:7777";', rust)
        self.assertIn("installer_connection", rust)
        self.assertIn("installer_request", rust)
        self.assertIn("installer_stream", rust)
        self.assertIn("allowlisted_path", rust)
        self.assertNotIn("Command::new", rust)
        self.assertNotIn("std::fs", rust)

    def test_launcher_prefers_shell_but_retains_chromium_fallback(self):
        launcher = LAUNCHER.read_text()
        self.assertIn('shutil.which("kyth-installer-shell")', launcher)
        self.assertIn('"--bootstrap-token", config._bootstrap_token', launcher)
        self.assertIn('"--session-token", SESSION_TOKEN', launcher)
        self.assertIn('"--no-sandbox"', launcher)
        self.assertIn("legacy Chromium fallback", launcher)

    def test_frontend_uses_backend_token_and_fixed_dev_proxy(self):
        api = (INSTALLER_WEB / "src/api.ts").read_text()
        vite = (INSTALLER_WEB / "vite.config.ts").read_text()
        self.assertIn('invoke<InstallerConnection>("installer_connection")', api)
        self.assertIn('X-Kyth-Session-Token', api)
        self.assertIn("session_token=", api)
        self.assertIn("127.0.0.1:7777", vite)

    def test_server_allows_only_tauri_cors_and_stream_auth(self):
        server = SERVER.read_text()
        self.assertIn('"http://tauri.localhost"', server)
        self.assertIn("Access-Control-Allow-Origin", server)
        self.assertIn("def do_OPTIONS", server)
        self.assertIn('parsed.path == "/api/stream"', server)
        self.assertIn('parsed.query).get("session_token")', server)
        self.assertNotIn('Access-Control-Allow-Origin", "*"', server)

    def test_server_has_opt_in_unix_transport_with_peer_credentials(self):
        server = SERVER.read_text()
        config = (ROOT / "src/kyth-installer/kyth_installer/config.py").read_text()
        self.assertIn("class UnixSocketServer", server)
        self.assertIn("SO_PEERCRED", server)
        self.assertIn("SOCKET_PATH", config)
        self.assertIn("SOCKET_GROUP", config)

    def test_image_build_copies_shell_from_isolated_builder(self):
        containerfile = (ROOT / "installer/Containerfile").read_text()
        self.assertIn("AS installer-web-builder", containerfile)
        self.assertIn("npm ci && npm run build", containerfile)
        self.assertIn("cargo build --release --locked", containerfile)
        self.assertIn("COPY --from=installer-web-builder", containerfile)
        build = (ROOT / "installer/build.sh").read_text()
        self.assertIn("webkit2gtk4.1", build)
        self.assertIn("gtk3", build)


if __name__ == "__main__":
    unittest.main()
