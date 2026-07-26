"""System-facing bootc queries.

This module owns command execution and cache access.  Interpretation and UI
policy belong in :mod:`bootc_policy`.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from kyth_shared.system.process import (
    _BOOTC_CACHE_TTL,
    _command_stdout,
    _probe_cached,
    _run_command,
)

REGISTRY = "ghcr.io/mrtrick37/kyth"


def nested_get(data: object, path: tuple[str, ...]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def walk_strings(data: object):
    if isinstance(data, str):
        yield data
    elif isinstance(data, dict):
        for value in data.values():
            yield from walk_strings(value)
    elif isinstance(data, list):
        for value in data:
            yield from walk_strings(value)


def fetch_status_text() -> str:
    for cmd in (["sudo", "-n", "bootc", "status"], ["bootc", "status"]):
        result = _run_command(cmd, timeout=10)
        if result is not None and result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return ""


def status_text() -> str:
    return _probe_cached("bootc-status-text", _BOOTC_CACHE_TTL, fetch_status_text)


def fetch_status_data() -> dict | None:
    for cmd in (
        ["sudo", "-n", "bootc", "status", "--json"],
        ["bootc", "status", "--json"],
    ):
        result = _run_command(cmd, timeout=10)
        if result is None or result.returncode != 0 or not result.stdout.strip():
            continue
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            continue
    return None


def status_data() -> dict | None:
    return _probe_cached("bootc-status-data", _BOOTC_CACHE_TTL, fetch_status_data)


def active_operation() -> str | None:
    result = _run_command(["ps", "-eo", "pid=,args="], timeout=5)
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return None
    for line in result.stdout.splitlines():
        text = line.strip()
        if " bootc " in f" {text} " and any(
            op in text
            for op in (" bootc upgrade", " bootc switch", " bootc rollback", " bootc reset")
        ):
            return text
    return None


def image_reference_from_status(
    data: dict | None, *, status_text: str = "", status_output: str = "",
) -> str | None:
    data = data or {}
    candidates = (
        ("status", "booted", "image", "reference"),
        ("status", "booted", "image", "image", "reference"),
        ("status", "booted", "image", "image", "image"),
        ("status", "booted", "image", "image"),
        ("status", "booted", "image"),
        ("spec", "image", "image"),
        ("spec", "image", "reference"),
    )
    for path in candidates:
        value = nested_get(data, path)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in walk_strings(data):
        if REGISTRY in value.strip():
            return value.strip()
    status_output = status_output or status_text
    if status_output:
        pattern = re.compile(
            rf"({re.escape(REGISTRY)}(?::[A-Za-z0-9._-]+)?"
            rf"(?:@sha256:[a-fA-F0-9]+)?)"
        )
        match = pattern.search(status_output)
        if match:
            return match.group(1)
    return None


def image_reference() -> str | None:
    data = status_data() or {}
    ref = image_reference_from_status(data)
    if ref:
        return ref
    ref = image_reference_from_status(data, status_output=status_text())
    if ref:
        return ref
    result = _run_command(["rpm-ostree", "status"], timeout=10)
    if result and result.returncode == 0:
        return image_reference_from_status({}, status_output=result.stdout)
    return None


def kernel_flavor() -> str:
    def fetch() -> str:
        try:
            with open("/usr/share/kyth/kernel-flavor") as fh:
                flavor = fh.read().strip().lower()
                if flavor in {"fedora", "cachy"}:
                    return flavor
        except OSError:
            pass
        return "cachy" if "cachy" in _command_stdout(["uname", "-r"]).lower() else "fedora"

    return _probe_cached("kernel-flavor", 60.0, fetch)


def has_deployment(section: str) -> bool:
    return nested_get(status_data() or {}, ("status", section)) is not None


def image_digest_from_status(data: dict | None, section: str) -> str | None:
    deployment = nested_get(data or {}, ("status", section)) or {}
    for path in (
        ("image", "imageDigest"), ("image", "digest"), ("imageDigest",), ("digest",),
    ):
        value = nested_get(deployment, path)
        if isinstance(value, str) and value.startswith("sha256:"):
            return value
    return None


def image_timestamp(section: str) -> str | None:
    deployment = nested_get(status_data() or {}, ("status", section)) or {}
    for path in (("image", "timestamp"), ("timestamp",)):
        value = nested_get(deployment, path)
        if isinstance(value, str) and value.strip():
            try:
                dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00")).astimezone()
                return dt.strftime("%Y-%m-%d %H:%M %Z")
            except (ValueError, OverflowError):
                return value.strip()
    return None


def image_digest(section: str) -> tuple[str, str] | None:
    value = image_digest_from_status(status_data(), section)
    return None if value is None else (value[7:19], value[7:])
