"""VPN connect helpers (openconnect / GlobalProtect SAML parsers).

Pure config/parsing — no Qt. Connect worker lives in ``services.workers.vpn``.
"""
from __future__ import annotations

import configparser
import os
import re
from urllib.parse import parse_qs

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


def gp_interface_from_log_line(line: str) -> str | None:
    """Return 'portal' or 'gateway' if line is a GP prelogin POST, else None."""
    m = _GP_PRELOGIN_IFACE_RE.search(line)
    if not m:
        return None
    return "portal" if m.group(1) == "global-protect" else "gateway"


def saml_url_from_log_line(line: str) -> str | None:
    m = _SAML_URL_RE.search(line)
    return m.group(1) if m else None


def _openconnect_base(protocol: str, os_emul: str) -> list[str]:
    return [
        "sudo",
        "-E",
        "-A",
        "/usr/bin/openconnect",
        "--protocol",
        protocol,
        "--os",
        os_emul,
        "--script",
        "/usr/libexec/kyth-vpnc-script",
    ]


def build_initial_command(
    gateway: str,
    protocol: str,
    os_emul: str,
    username: str = "",
    password: str = "",
) -> tuple[list[str], str]:
    """Build the first openconnect probe/connection command."""
    command = _openconnect_base(protocol, os_emul)
    if username:
        command += ["--user", username]
    if password:
        command.append("--passwd-on-stdin")
    command.append(gateway)
    return command, password


def build_gateway_probe_command(
    gateway: str,
    protocol: str,
    os_emul: str,
    username: str = "",
) -> list[str]:
    """Build the gateway-specific probe used after portal SAML succeeds."""
    command = _openconnect_base(protocol, os_emul)
    command += ["--usergroup", "gateway"]
    if username:
        command += ["--user", username]
    command.append(gateway)
    return command


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
    command = _openconnect_base(protocol, os_emul)
    stdin_text = ""
    if protocol == "gp" and field and value:
        command += ["--passwd-on-stdin", "--usergroup", f"{interface}:{field}"]
        stdin_text = value
    else:
        command += ["--cookie", cookie]
    username = saml_username or configured_username
    if username:
        command += ["--user", username]
    command.append(gateway)
    return command, stdin_text, username
