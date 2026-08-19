"""VPN connect helpers (openconnect / GlobalProtect SAML parsers).

Pure config/parsing — no Qt. Connect worker lives in ``services.workers.vpn``.
"""
from __future__ import annotations

import configparser
import os
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .privileged import openconnect_action

_VPN_CONFIG = os.path.expanduser("~/.config/kyth-vpn-connect")
VPN_PROTOCOLS = ["gp", "anyconnect", "pulse", "nc", "f5", "fortinet", "array"]
VPN_OS_OPTIONS = ["win", "linux", "mac"]

# Compat aliases used by page
_VPN_PROTOCOLS = VPN_PROTOCOLS
_VPN_OS_OPTIONS = VPN_OS_OPTIONS

_SAML_URL_RE = re.compile(r"SAML REDIRECT.*?via (https?://\S+)")
# Which GP interface openconnect was probing when SAML was requested.
# A prelogin-cookie is only valid on the interface that issued it, so the
# reconnect must use portal:<host> vs gateway:<host> accordingly.
_GP_PRELOGIN_IFACE_RE = re.compile(r"POST https?://[^/]+/(global-protect|ssl-vpn)/prelogin\.esp")
_GP_SAML_FIELDS = frozenset({
    "preloginuserauthcookie",
    "portal-userauthcookie",
    "cas",
    "prelogin-cookie",
})
_SAML_ACS_PATH = "/SAML20/SP/ACS"
_MAX_SAML_FORM_BYTES = 2 * 1024 * 1024
_MAX_SAML_RESPONSE_BYTES = 2 * 1024 * 1024


def _https_origin(url: str, *, bare_host: bool = False) -> tuple[str, int]:
    candidate = f"https://{url}" if bare_host and "://" not in url else url
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("SAML ACS destination must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("SAML ACS destination must not contain credentials")
    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise ValueError("SAML ACS destination has an invalid port") from exc
    try:
        hostname = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("SAML ACS destination has an invalid hostname") from exc
    return hostname, port


def validate_saml_acs_url(action_url: str, expected_gateway: str) -> str:
    """Return a validated ACS URL bound to the configured VPN gateway origin."""
    parsed = urlsplit(action_url)
    if parsed.fragment:
        raise ValueError("SAML ACS destination must not contain a fragment")
    if parsed.path.rstrip("/") != _SAML_ACS_PATH:
        raise ValueError("SAML ACS destination has an unexpected path")
    if _https_origin(action_url) != _https_origin(expected_gateway, bare_host=True):
        raise ValueError("SAML ACS destination does not match the VPN gateway")
    return action_url


class _SameOriginRedirectHandler(HTTPRedirectHandler):
    def __init__(self, expected_gateway: str) -> None:
        super().__init__()
        self._origin = _https_origin(expected_gateway, bare_host=True)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _https_origin(newurl) != self._origin:
            raise ValueError("SAML ACS redirect left the VPN gateway origin")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def load_vpn_config() -> dict:
    cfg = configparser.ConfigParser()
    if os.path.exists(_VPN_CONFIG):
        cfg.read(_VPN_CONFIG)
    return dict(cfg["vpn"]) if "vpn" in cfg else {}


_load_vpn_config = load_vpn_config


def save_vpn_config(gateway: str, protocol: str, os_emul: str, username: str) -> None:
    cfg = configparser.ConfigParser()
    cfg["vpn"] = {
        "gateway": gateway,
        "protocol": protocol,
        "os": os_emul,
        "username": username,
    }
    with open(_VPN_CONFIG, "w") as f:
        cfg.write(f)


_save_vpn_config = save_vpn_config


def parse_gp_saml_cookie(cookie: str) -> tuple[str, str, str]:
    """Return (field_name, value, username) from a GP SAML cookie blob."""
    raw = cookie.strip()
    if not raw:
        return "", "", ""
    params = parse_qs(raw, keep_blank_values=True)
    username = params.get("saml-username", [""])[0]
    for name in _GP_SAML_FIELDS:
        if name in params and params[name]:
            return name, params[name][0], username
    if "=" in raw:
        name, value = raw.split("=", 1)
        name = name.strip()
        if name in _GP_SAML_FIELDS and value:
            return name, value, ""
    return "prelogin-cookie", raw, ""


_parse_gp_saml_cookie = parse_gp_saml_cookie


def redact_vpn_log_line(line: str) -> str:
    return re.sub(
        r"(GlobalProtect login returned (?:portal-userauthcookie|portal-prelogonuserauthcookie|prelogin-cookie|preloginuserauthcookie|cas)=).*",
        r"\1<redacted>",
        line,
    )


_redact_vpn_log_line = redact_vpn_log_line


def vpn_line_is_connected(line: str) -> bool:
    lo = line.lower()
    return any(
        marker in lo
        for marker in (
            "connected as",
            "established dtls",
            "established cstp",
            "esp session established",
            "esp tunnel connected",
            "configured as",
        )
    )


_vpn_line_is_connected = vpn_line_is_connected


@dataclass(frozen=True)
class VpnStatusView:
    text: str
    style: str


def vpn_status_view(state: str) -> VpnStatusView:
    if state == "connected":
        return VpnStatusView("● Connected", "status-ok")
    if state == "connecting":
        return VpnStatusView("● Connecting…", "status-warn")
    return VpnStatusView("● Disconnected", "status-dim")


def gp_interface_from_log_line(line: str) -> str | None:
    """Return 'portal' or 'gateway' if line is a GP prelogin POST, else None."""
    m = _GP_PRELOGIN_IFACE_RE.search(line)
    if not m:
        return None
    return "portal" if m.group(1) == "global-protect" else "gateway"


def saml_url_from_log_line(line: str) -> str | None:
    m = _SAML_URL_RE.search(line)
    return m.group(1) if m else None


def build_initial_command(
    gateway: str,
    protocol: str,
    os_emul: str,
    username: str = "",
    password: str = "",
) -> tuple[list[str], str]:
    """Build the first openconnect probe/connection command."""
    command = openconnect_action(
        gateway=gateway,
        protocol=protocol,
        os_emulation=os_emul,
        username=username,
        password_stdin=bool(password),
    ).command()
    return command, password


def build_gateway_probe_command(
    gateway: str,
    protocol: str,
    os_emul: str,
    username: str = "",
) -> list[str]:
    """Build the gateway-specific probe used after portal SAML succeeds."""
    return openconnect_action(
        gateway=gateway,
        protocol=protocol,
        os_emulation=os_emul,
        username=username,
        usergroup="gateway",
    ).command()


def build_saml_reconnect_command(
    gateway: str,
    protocol: str,
    os_emul: str,
    interface: str,
    cookie: str,
    configured_username: str = "",
) -> tuple[list[str], str, str]:
    """Build the authenticated reconnect and return command/stdin/username."""
    field, value, saml_username = parse_gp_saml_cookie(cookie)
    password_stdin = protocol == "gp" and bool(field and value)
    stdin_text = value if password_stdin else cookie
    username = saml_username or configured_username
    command = openconnect_action(
        gateway=gateway,
        protocol=protocol,
        os_emulation=os_emul,
        username=username,
        usergroup=f"{interface}:{field}" if protocol == "gp" and field and value else "",
        password_stdin=password_stdin,
        cookie="" if password_stdin else cookie,
    ).command()
    return command, stdin_text, username


def parse_saml_acs_response(headers: dict[str, str], body_text: str) -> str | None:
    """Parses response headers and body to extract a GlobalProtect auth token.

    Returns the urlencoded cookie string if found, otherwise None.
    """
    lower_headers = {k.lower(): v for k, v in headers.items()}
    for name in (
        "prelogin-cookie",
        "portal-userauthcookie",
        "cas",
        "preloginuserauthcookie",
    ):
        if lower_headers.get(name):
            return urlencode(
                {
                    name: lower_headers[name],
                    "saml-username": lower_headers.get("saml-username", ""),
                }
            )

    for name in (
        "prelogin-cookie",
        "portal-userauthcookie",
        "cas",
        "preloginuserauthcookie",
    ):
        m = re.search(
            rf"<{re.escape(name)}>([^<]+)</{re.escape(name)}>", body_text, re.I
        )
        if m:
            user_match = re.search(
                r"<saml-username>([^<]+)</saml-username>", body_text, re.I
            )
            return urlencode(
                {
                    name: m.group(1).strip(),
                    "saml-username": (
                        user_match.group(1).strip() if user_match else ""
                    ),
                }
            )
    return None


def replay_saml_acs(action_url: str, body: str, expected_gateway: str) -> str | None:
    """Replays the SAML ACS response to the VPN portal and returns the cookie string if found."""
    action_url = validate_saml_acs_url(action_url, expected_gateway)
    encoded_body = body.encode("utf-8")
    if len(encoded_body) > _MAX_SAML_FORM_BYTES:
        raise ValueError("SAML ACS form is too large")
    if not parse_qs(body, keep_blank_values=True).get("SAMLResponse"):
        raise ValueError("SAML ACS form does not contain SAMLResponse")
    req = Request(
        action_url,
        data=encoded_body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "PAN GlobalProtect",
        },
        method="POST",
    )
    opener = build_opener(_SameOriginRedirectHandler(expected_gateway))
    with opener.open(req, timeout=30) as resp:
        headers = {k.lower(): v for k, v in resp.headers.items()}
        response_body = resp.read(_MAX_SAML_RESPONSE_BYTES + 1)
        if len(response_body) > _MAX_SAML_RESPONSE_BYTES:
            raise ValueError("SAML ACS response is too large")
        text = response_body.decode("utf-8", errors="replace")

    return parse_saml_acs_response(headers, text)
