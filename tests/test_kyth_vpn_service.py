"""Pure VPN parser helpers (no openconnect / no WebEngine)."""
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services.vpn import (  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
