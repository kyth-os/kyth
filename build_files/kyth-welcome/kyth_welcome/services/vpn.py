"""VPN connect helpers (openconnect / GlobalProtect SAML parsers).

Pure config/parsing is importable without Qt; the connect worker needs runtime.
"""
from __future__ import annotations

import configparser
import os
import re
import subprocess
from urllib.parse import parse_qs

from ..qt import Signal
from .runtime import TrackedThread

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


class VpnConnectWorker(TrackedThread):
    line = Signal(str)
    done = Signal(int)
    saml_required = Signal(str)

    def __init__(self, cmd: list[str], password: str = ""):
        super().__init__()
        self._cmd = cmd
        self._password = password
        self._proc: subprocess.Popen | None = None

    def run(self) -> None:
        env = os.environ.copy()
        env.setdefault("SUDO_ASKPASS", "/usr/bin/ksshaskpass")
        env.setdefault("SUDO_PROMPT", "Password:")
        stdin_pipe = subprocess.PIPE if self._password else subprocess.DEVNULL
        try:
            self._proc = subprocess.Popen(
                self._cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=stdin_pipe,
                text=True,
                bufsize=1,
                env=env,
                cwd="/tmp",
            )
            if self._password and self._proc.stdin:
                self._proc.stdin.write(self._password + "\n")
                self._proc.stdin.close()
            assert self._proc.stdout
            for ln in self._proc.stdout:
                clean = ln.rstrip()
                self.line.emit(clean)
                url = saml_url_from_log_line(clean)
                if url:
                    self.saml_required.emit(url)
            self._proc.wait()
            self.done.emit(self._proc.returncode)
        except Exception as exc:
            self.line.emit(f"Error: {exc}")
            self.done.emit(1)

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


# Compat alias
_VpnConnectWorker = VpnConnectWorker
