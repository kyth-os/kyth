"""Diagnostics scrub — central scrub before upload."""
import re

def scrub_logs(text: str) -> str:
    # Remove hostname, serial, SSID
    text = re.sub(r"hostname[:=]\s*\S+", "hostname=redacted", text, flags=re.I)
    text = re.sub(r"serial[:=]\s*\S+", "serial=redacted", text, flags=re.I)
    text = re.sub(r"SSID[:=]\s*\S+", "SSID=redacted", text, flags=re.I)
    text = re.sub(r"[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}", "xx:xx:xx:xx:xx:xx", text)
    return text
