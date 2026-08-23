"""System-facing bootc queries.

This module owns command execution and cache access.  Interpretation and UI
policy belong in :mod:`bootc_policy`.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any
from kyth_shared.runtime_output import parse_json_object

from kyth_shared.system.process import (
    BOOTC_CACHE_TTL,
    command_stdout,
    probe_cached,
    run_command,
)

REGISTRY = "ghcr.io/kyth-os/kyth"


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


def _status_commands(*, json_mode: bool) -> tuple[list[str], ...]:
    """bootc status command candidates.

    Unprivileged callers must go through ``sudo -n kyth-bootc-guard`` (the
    only NOPASSWD path). Root-context units already have euid 0; invoking
    sudo from those is unnecessary and fails in hardened sandboxes
    (empty CapabilityBoundingSet + NoNewPrivileges → EPERM on /etc/sudoers).
    """
    guard_op = "status-json" if json_mode else "status"
    guard = ["/usr/bin/kyth-bootc-guard", guard_op]
    bootc = ["bootc", "status", "--json"] if json_mode else ["bootc", "status"]
    if os.geteuid() == 0:
        return (guard, bootc)
    return (["sudo", "-n", *guard], bootc)


def fetch_status_text() -> str:
    # `bootc status` requires root even for a read (bootc 1.16+ takes a
    # sysroot write-lock while querying privilege) — there is no NOPASSWD
    # rule for raw `bootc status` (only the fixed kyth-bootc-guard
    # operations), so a bare `sudo -n bootc status` always fails and just
    # spams an auth-failure audit line on every probe. Route through the
    # guard, which does have a NOPASSWD rule. Keep the unprivileged
    # fallback only in case the guard binary itself is ever missing.
    # Never take that write-lock while an upgrade is running: Hub probes
    # otherwise convoy behind bootc/ostree and the upgrade hits its timeout.
    if active_operation():
        return ""
    for cmd in _status_commands(json_mode=False):
        result = run_command(cmd, timeout=10)
        if result is not None and result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return ""


def status_text() -> str:
    return probe_cached("bootc-status-text", BOOTC_CACHE_TTL, fetch_status_text)


def fetch_status_data() -> dict | None:
    # See fetch_status_text() above: route through kyth-bootc-guard's
    # NOPASSWD status-json operation instead of a bare `sudo -n bootc
    # status --json`, which has no matching sudoers rule and always fails.
    if active_operation():
        return None
    for cmd in _status_commands(json_mode=True):
        result = run_command(cmd, timeout=10)
        if result is None or result.returncode != 0 or not result.stdout.strip():
            continue
        parsed = parse_json_object(result.stdout)
        if parsed is not None:
            return parsed
    return None


def status_data() -> dict | None:
    return probe_cached("bootc-status-data", BOOTC_CACHE_TTL, fetch_status_data)


# Commands that take ostree's sysroot write-lock. Hub `bootc status`
# probes must not run while any of these are alive or they convoy
# behind the lock and the GUI updater hits its timeout.
# argv0 is often /usr/bin/bootc, so a leading-space " bootc upgrade"
# marker misses the real process and lets Hub take the lock.
_BOOTC_LOCK_RE = re.compile(
    r"(?:^|[\s/])bootc\s+(upgrade|switch|rollback|reset)(?:\s|$)"
)
_FINALIZE_MARKER = "ostree admin finalize-staged"


def holds_sysroot_lock(cmdline: str) -> bool:
    """True if *cmdline* is a bootc/ostree process holding the sysroot lock."""
    text = cmdline.strip()
    if _FINALIZE_MARKER in text:
        return True
    return _BOOTC_LOCK_RE.search(text) is not None


def active_operation() -> str | None:
    result = run_command(["ps", "-eo", "pid=,args="], timeout=5)
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return None
    for line in result.stdout.splitlines():
        text = line.strip()
        if holds_sysroot_lock(text):
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
    result = run_command(["rpm-ostree", "status"], timeout=10)
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
        return "cachy" if "cachy" in command_stdout(["uname", "-r"]).lower() else "fedora"

    return probe_cached("kernel-flavor", 600.0, fetch)


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
