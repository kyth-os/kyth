"""Diagnostics scrub — central scrub before upload."""

import logging
import ipaddress
import os
import re

logger = logging.getLogger(__name__)


_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?-----END [^-\r\n]*PRIVATE KEY-----",
    re.DOTALL,
)
_SENSITIVE_HEADER_RE = re.compile(
    r"(?im)(\b(?:authorization|proxy-authorization|cookie|set-cookie)\s*[:=]\s*)[^\r\n]+"
)
_AUTH_VALUE_RE = re.compile(
    r"(?i)(\b(?:authorization|proxy-authorization)\s*[:=]\s*)(?:bearer|basic|token)\s+\S+"
)
_SECRET_VALUE_RE = re.compile(
    r"(?i)([\"']?(?:access[_-]?token|refresh[_-]?token|id[_-]?token|bearer|password|passwd|passphrase|"
    r"client[_-]?secret|api[_-]?key|private[_-]?key|auth[_-]?cookie|session[_-]?cookie|cookie|secret)"
    r"[\"']?\s*[:=]\s*)(\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;&]+)"
)
_SECRET_FLAG_RE = re.compile(
    r"(?i)(--(?:cookie|password|passwd|token|client-secret|api-key)(?:=|\s+))\S+"
)
_SECRET_QUERY_RE = re.compile(
    r"(?i)([?&](?:access_token|refresh_token|id_token|token|password|passwd|secret|cookie|api_key|client_secret)=)[^&#\s]+"
)
_URL_CREDENTIAL_RE = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)[^/@\s:]+:[^/@\s]+@")
_IPV6_CANDIDATE_RE = re.compile(
    r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]*:){2,}[0-9A-Fa-f]*(?![0-9A-Fa-f:])"
)


def _redact_secret_value(match: re.Match[str]) -> str:
    value = match.group(2)
    replacement = '"[redacted]"' if value.startswith('"') else "'[redacted]'" if value.startswith("'") else "[redacted]"
    return f"{match.group(1)}{replacement}"


def _redact_ipv6(match: re.Match[str]) -> str:
    candidate = match.group(0)
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return candidate
    return "xxxx:xxxx:xxxx:xxxx::xxxx" if address.version == 6 else candidate

def scrub_logs(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("diagnostic report must be text")
    # Secrets first, before broader identity substitutions alter their shape.
    text = _PRIVATE_KEY_RE.sub("[private key redacted]", text)
    text = _AUTH_VALUE_RE.sub(r"\1[redacted]", text)
    text = _SENSITIVE_HEADER_RE.sub(r"\1[redacted]", text)
    text = _SECRET_VALUE_RE.sub(_redact_secret_value, text)
    text = _SECRET_FLAG_RE.sub(r"\1[redacted]", text)
    text = _SECRET_QUERY_RE.sub(r"\1[redacted]", text)
    text = _URL_CREDENTIAL_RE.sub(r"\1[credentials-redacted]@", text)
    # Hostname, serial, SSID (case-insensitive, keep key but redact value)
    text = re.sub(r"hostname[:=]\s*\S+", "hostname=redacted", text, flags=re.I)
    text = re.sub(r"serial[:=]\s*\S+", "serial=redacted", text, flags=re.I)
    text = re.sub(r"Serial\s*[:=]\s*\S+", "Serial: [scrubbed]", text, flags=re.I)
    text = re.sub(r"SSID[:=]\s*\S+", "SSID=redacted", text, flags=re.I)
    text = re.sub(r"SSID\s*[:=]\s*\S+", "SSID: [scrubbed]", text, flags=re.I)
    # MAC
    text = re.sub(r"[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}", "xx:xx:xx:xx:xx:xx", text)
    # IPv4
    text = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "xxx.xxx.xxx.xxx", text)
    # IPv6
    text = _IPV6_CANDIDATE_RE.sub(_redact_ipv6, text)
    # Email
    text = re.sub(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "redacted@example.com", text)
    # UUID
    text = re.sub(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", text)
    # Home path (/home and Fedora's /var/home layout)
    text = re.sub(r"(?<!/)(/var/home|/home)/[^/\s:]+", r"\1/redacted", text)
    # Hostname literal (current host) if present
    try:
        import socket as _socket
        host = _socket.gethostname()
        if host and len(host) > 2:
            text = text.replace(host, "[hostname]")
    except Exception:  # nosec B110 -- best-effort, failure here is non-fatal by design
        pass
    # XDG HOME fallback env
    try:
        user = os.environ.get("USER") or os.environ.get("USERNAME")
        if user and len(user) > 1:
            # Avoid double-redacting already handled /home path
            text = re.sub(rf"\b{re.escape(user)}\b", "redacted", text)
    except Exception:
        logger.debug("handled expected exception", exc_info=True)
        pass
    return text
