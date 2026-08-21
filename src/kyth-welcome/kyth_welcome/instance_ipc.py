"""Pure helpers for System Hub single-instance activate messages.

Kept Qt-free so unit tests can cover the wire format without a display.
"""
from __future__ import annotations


def encode_activate_message(page: str | None) -> bytes:
    """Encode a second-launch activate payload (optional --page key)."""
    return f"show:{page or ''}".encode()


def decode_activate_message(payload: bytes) -> str | None:
    """Return a page key to navigate to, or None for raise-only."""
    text = payload.decode("utf-8", errors="replace").strip()
    if not text.startswith("show"):
        return None
    if ":" not in text:
        return None
    page = text.split(":", 1)[1].strip()
    return page or None
