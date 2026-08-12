"""Diagnostics scrub — central scrub before upload."""

import re
import os

def scrub_logs(text: str) -> str:
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
    # Email
    text = re.sub(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "redacted@example.com", text)
    # UUID
    text = re.sub(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", text)
    # Home path  /home/<user>/ -> /home/redacted/
    text = re.sub(r"/home/[^/\s:]+", "/home/redacted", text)
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
        pass
    return text
