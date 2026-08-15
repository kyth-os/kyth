"""Fonts ready helper — Nobara msttcorefonts parity (N35)."""
from __future__ import annotations
from kyth_shared.commands import run

def fonts_ready() -> tuple[bool, str]:
    try:
        r = run(["fc-list", ":family=Noto Sans"], capture_output=True, text=True, timeout=5, check=False)
        has_noto = bool(r.stdout.strip()) if r.returncode == 0 else False
        r2 = run(["fc-list", ":family=Arial"], capture_output=True, text=True, timeout=5, check=False)
        has_ms = bool(r2.stdout.strip()) if r2.returncode == 0 else False
        if has_noto and has_ms:
            return True, "Noto + MS fonts ready"
        if has_noto:
            return False, "Noto ready, MS via ujust install-ms-fonts"
        return False, "fonts check pending"
    except Exception as exc:
        return False, str(exc)
