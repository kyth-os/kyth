"""VPN helpers and lifecycle regressions (no openconnect / no WebEngine)."""
import ast
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services.vpn import (  # noqa: E402
    build_gateway_probe_command,
    build_initial_command,
    build_saml_reconnect_command,
    gp_interface_from_log_line,
    load_vpn_config,
    parse_gp_saml_cookie,
    redact_vpn_log_line,
    saml_url_from_log_line,
    save_vpn_config,
    vpn_line_is_connected,
)


class VpnParserTests(unittest.TestCase):
    def test_parse_gp_saml_cookie_query(self):
        field, value, user = parse_gp_saml_cookie(
            "prelogin-cookie=tok123&saml-username=alice"
        )
        self.assertEqual(field, "prelogin-cookie")
        self.assertEqual(value, "tok123")
        self.assertEqual(user, "alice")

    def test_parse_gp_saml_cookie_raw_pair(self):
        field, value, user = parse_gp_saml_cookie("cas=xyz")
        self.assertEqual(field, "cas")
        self.assertEqual(value, "xyz")
        self.assertEqual(user, "")

    def test_parse_gp_saml_cookie_empty(self):
        self.assertEqual(parse_gp_saml_cookie(""), ("", "", ""))

    def test_redact_vpn_log_line(self):
        line = "GlobalProtect login returned prelogin-cookie=SECRETS"
        redacted = redact_vpn_log_line(line)
        self.assertIn("<redacted>", redacted)
        self.assertNotIn("SECRETS", redacted)

    def test_vpn_line_is_connected(self):
        self.assertTrue(vpn_line_is_connected("Connected as user@example"))
        self.assertTrue(vpn_line_is_connected("Established DTLS connection"))
        self.assertFalse(vpn_line_is_connected("Authenticating..."))

    def test_saml_url_from_log_line(self):
        url = saml_url_from_log_line(
            "SAML REDIRECT authentication will be required via https://sso.example/login"
        )
        self.assertEqual(url, "https://sso.example/login")
        self.assertIsNone(saml_url_from_log_line("plain line"))

    def test_gp_interface_from_log_line(self):
        self.assertEqual(
            gp_interface_from_log_line(
                "POST https://vpn.example/global-protect/prelogin.esp"
            ),
            "portal",
        )
        self.assertEqual(
            gp_interface_from_log_line(
                "POST https://vpn.example/ssl-vpn/prelogin.esp"
            ),
            "gateway",
        )
        self.assertIsNone(gp_interface_from_log_line("GET https://example/"))

    def test_initial_command_preserves_askpass_and_password_stdin(self):
        command, stdin_text = build_initial_command(
            "vpn.example", "gp", "win", "alice", "secret"
        )
        self.assertEqual(command[:4], ["sudo", "-E", "-A", "/usr/bin/openconnect"])
        self.assertIn("--passwd-on-stdin", command)
        user_index = command.index("--user")
        self.assertEqual(command[user_index + 1], "alice")
        self.assertEqual(command[-1], "vpn.example")
        self.assertEqual(stdin_text, "secret")

    def test_saml_reconnect_uses_issuing_interface_and_saml_identity(self):
        command, stdin_text, username = build_saml_reconnect_command(
            "vpn.example",
            "gp",
            "win",
            "gateway",
            "prelogin-cookie=token&saml-username=saml-user",
            "configured-user",
        )
        self.assertIn("gateway:prelogin-cookie", command)
        self.assertEqual(stdin_text, "token")
        self.assertEqual(username, "saml-user")
        self.assertEqual(command[-3:], ["--user", "saml-user", "vpn.example"])

    def test_gateway_probe_targets_gateway_usergroup(self):
        command = build_gateway_probe_command(
            "vpn.example", "gp", "win", "alice"
        )
        group_index = command.index("--usergroup")
        self.assertEqual(command[group_index + 1], "gateway")
        self.assertEqual(command[-1], "vpn.example")


class VpnConfigTests(unittest.TestCase):
    def test_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = pathlib.Path(tmp) / "kyth-vpn-connect"
            with patch("kyth_welcome.services.vpn._VPN_CONFIG", str(cfg)):
                save_vpn_config("vpn.example", "gp", "win", "alice")
                loaded = load_vpn_config()
            self.assertEqual(loaded["gateway"], "vpn.example")
            self.assertEqual(loaded["protocol"], "gp")
            self.assertEqual(loaded["os"], "win")
            self.assertEqual(loaded["username"], "alice")


class VpnWebEngineLifecycleTests(unittest.TestCase):
    def test_parent_owned_webengine_objects_are_not_deferred_twice(self):
        """Qt owns page/profile teardown after each SAML dialog closes."""
        paths = (
            ROOT
            / "build_files"
            / "kyth-welcome"
            / "kyth_welcome"
            / "page_vpn_saml_dialog.py",
        )

        for path in paths:
            with self.subTest(path=path.relative_to(ROOT)):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                teardowns = [
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "_teardown_webengine"
                ]
                self.assertEqual(len(teardowns), 1)

                deferred_children = []
                for node in ast.walk(teardowns[0]):
                    if not isinstance(node, ast.Call):
                        continue
                    func = node.func
                    if not isinstance(func, ast.Attribute) or func.attr != "deleteLater":
                        continue
                    owner = func.value
                    if (
                        isinstance(owner, ast.Attribute)
                        and isinstance(owner.value, ast.Name)
                        and owner.value.id == "self"
                        and owner.attr in {"_page", "_profile"}
                    ):
                        deferred_children.append(owner.attr)

                self.assertEqual(
                    deferred_children,
                    [],
                    "page/profile are parent-owned and must not also receive deleteLater()",
                )

    def test_legacy_vpn_command_delegates_to_system_hub(self):
        launcher = (
            ROOT / "build_files" / "kyth-vpn-connect" / "kyth-vpn-connect"
        ).read_text(encoding="utf-8")
        tree = ast.parse(launcher)

        self.assertIn("kyth_welcome.vpn_app", launcher)
        self.assertFalse(
            any(
                isinstance(node, ast.ClassDef)
                and node.name in {"MainWindow", "SamlBrowserDialog"}
                for node in ast.walk(tree)
            ),
            "compatibility launcher must not grow a second VPN UI",
        )

        vpn_app = (
            ROOT
            / "build_files"
            / "kyth-welcome"
            / "kyth_welcome"
            / "vpn_app.py"
        ).read_text(encoding="utf-8")
        self.assertIn("self.vpn_page = VpnPage()", vpn_app)
        self.assertIn("QLocalServer", vpn_app)
        self.assertIn("worker.isRunning()", vpn_app)


if __name__ == "__main__":
    unittest.main()
