"""Deployment history for System Restore timeline (pure)."""
from __future__ import annotations
import logging
import subprocess

from typing import Any
from urllib.parse import urlparse

from .bootc_query import image_digest_from_status, image_timestamp, nested_get, status_data
from .bootc_policy import branch_from_ref

logger = logging.getLogger(__name__)


def _deployment_info(data: dict, section: str, label: str, status_text: str) -> dict[str, Any]:
    dep = nested_get(data, ("status", section))
    if dep is None:
        return {"section": section, "label": label, "available": False}
    # Try multiple paths for ref
    ref = None
    for path in (("image", "reference"), ("image", "image"), ("image", "image", "reference"), ("image",)):
        v = nested_get(dep, path)
        if isinstance(v, str) and v.strip():
            ref = v.strip()
            break
        if isinstance(v, dict):
            # nested image.image
            inner = v.get("reference") or v.get("image")
            if isinstance(inner, str) and inner.strip():
                ref = inner.strip()
                break
    if not ref:
        # Fallback walk strings
        for s in _walk_strings(dep):
            if _is_ghcr_reference(s):
                ref = s
                break
    branch = branch_from_ref(ref) if ref else None
    ts = image_timestamp(section)
    digest = image_digest_from_status(data, section)
    short = digest[0] if digest else None
    return {
        "section": section,
        "label": label,
        "available": True,
        "reference": ref,
        "branch": branch,
        "timestamp": ts,
        "digest": digest[1] if digest else None,
        "short_digest": short,
        "status_text": status_text,
    }


def _is_ghcr_reference(value: str) -> bool:
    s = value.strip()
    if not s:
        return False

    parsed = urlparse(s)
    if parsed.hostname:
        return parsed.hostname.lower() == "ghcr.io"

    first_segment = s.split("/", 1)[0]
    return first_segment.lower() == "ghcr.io"


def _walk_strings(data: object):
    if isinstance(data, str):
        yield data
    elif isinstance(data, dict):
        for v in data.values():
            yield from _walk_strings(v)
    elif isinstance(data, list):
        for v in data:
            yield from _walk_strings(v)


def deployment_history() -> list[dict[str, Any]]:
    """Return ordered timeline: booted, staged, rollback."""
    data = status_data() or {}
    status_text = ""
    try:
        from .process import command_stdout
        status_text = command_stdout(["bootc", "status"], timeout=5) or ""
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError, ImportError):
        logger.debug("handled expected exception", exc_info=True)
        pass
    history: list[dict[str, Any]] = []
    for section, label in (("booted", "Current (booted)"), ("staged", "Staged (next boot)"), ("rollback", "Previous (rollback)")):
        info = _deployment_info(data, section, label, status_text)
        history.append(info)
    return history


def has_any_rollback() -> bool:
    data = status_data() or {}
    return nested_get(data, ("status", "rollback")) is not None
