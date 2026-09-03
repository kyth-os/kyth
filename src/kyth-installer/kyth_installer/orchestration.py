"""Compatibility adapter for Rust-owned installer orchestration decisions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from shutil import which as _which
from typing import Any

from .runner import run_command
from .system import _as_root


_HELPER = "kyth-installer-exec"


def native_operation(operation: str, payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Call the typed native helper, or return ``None`` only when absent.

    Once the helper is installed, malformed output and command failures are
    errors. Falling back after a partial or malformed native decision would
    let the Python compatibility layer disagree with Rust about destructive
    state transitions.
    """
    if _which(_HELPER) is None:
        return None
    try:
        result = run_command(
            _as_root([_HELPER, "--operation", operation]),
            input=json.dumps(dict(payload), separators=(",", ":")),
            text=True,
            capture_output=True,
            check=True,
            timeout=30,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        raise RuntimeError(f"native installer {operation} operation failed: {exc}") from exc
    raw = (result.stdout or "").strip()
    if not raw:
        raise RuntimeError(f"native installer {operation} operation returned no response")
    try:
        response = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"native installer {operation} operation returned malformed JSON"
        ) from exc
    if not isinstance(response, dict):
        raise RuntimeError(f"native installer {operation} operation returned a non-object")
    return response


def decision(action: str, **payload: Any) -> dict[str, Any] | None:
    """Request one Rust orchestration decision."""
    return native_operation("orchestration", {"action": action, **payload})


def power_check() -> dict[str, Any] | None:
    """Request the Rust-owned live power-supply probe."""
    return native_operation("power-check", {})
