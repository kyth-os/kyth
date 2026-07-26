"""Compatibility façade for bootc query, policy, and operation helpers.

New code should import pure decisions from ``bootc_policy`` and system-facing
queries from ``bootc_query``.  Existing private names remain available while
callers migrate.
"""
from __future__ import annotations

from ..commands import run as run_command
from kyth_shared.system.process import _BOOTC_CACHE_TTL, _command_stdout, _probe_cached
from kyth_shared.system import bootc_query as query
from kyth_shared.system.bootc_policy import (
    BranchCardView,
    BranchesView,
    REGISTRY,
    UpdateAvailabilityView,
    branch_display_name,
    branch_from_ref,
    branches_view,
    cancel_block_reason,
    default_phase,
    image_tag_for_channel,
    image_tag_for_kernel,
    parse_update_phase,
    update_availability_view,
)

nested_get = query.nested_get
_nested_get = nested_get
walk_strings = query.walk_strings
_walk_strings = walk_strings
image_reference_from_status = query.image_reference_from_status
image_digest_from_status = query.image_digest_from_status


def _fetch_bootc_status_text() -> str:
    return query.fetch_status_text()


def _bootc_status_text() -> str:
    # Keep patchable compatibility boundaries used by probes and tests.
    return _probe_cached("bootc-status-text", _BOOTC_CACHE_TTL, _fetch_bootc_status_text)


def _fetch_bootc_status_data() -> dict | None:
    return query.fetch_status_data()


def _bootc_status_data() -> dict | None:
    return _probe_cached("bootc-status-data", _BOOTC_CACHE_TTL, _fetch_bootc_status_data)


def fetch_bootc_status_data_uncached() -> dict | None:
    return _fetch_bootc_status_data()


def _active_bootc_operation() -> str | None:
    return query.active_operation()


def _default_phase(mode: str) -> str:
    return default_phase(mode)


def _bootc_proxy_running() -> bool:
    try:
        result = run_command(
            ["pgrep", "-f", "skopeo.*image-proxy"],
            capture_output=True, timeout=2, check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def _parse_update_phase(line: str, mode: str) -> str | None:
    return parse_update_phase(line, mode)


def _bootc_cancel_block_reason(mode: str, phase: str) -> str:
    return cancel_block_reason(mode, phase)


def _bootc_image_reference() -> str | None:
    data = _bootc_status_data() or {}
    ref = query.image_reference_from_status(data)
    if ref:
        return ref
    ref = query.image_reference_from_status(data, status_output=_bootc_status_text())
    if ref:
        return ref
    # Preserve the compatibility module's patchable status seams while
    # delegating the fallback query to the query adapter.
    return query.image_reference()


def _branch_from_ref(ref: str | None) -> str | None:
    return branch_from_ref(ref)


def _branch_display_name(tag: str | None) -> str:
    return branch_display_name(tag)


def _current_branch() -> str | None:
    return _probe_cached(
        "bootc-branch", _BOOTC_CACHE_TTL,
        lambda: branch_from_ref(_bootc_image_reference()),
    )


def _current_kernel_flavor() -> str:
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


def _image_tag_for_channel(channel: str, flavor: str | None = None) -> str:
    return image_tag_for_channel(channel, flavor or _current_kernel_flavor())


def _image_tag_for_kernel(flavor: str) -> str:
    return image_tag_for_kernel(flavor, _current_branch())


def _has_staged_update() -> bool:
    return nested_get(_bootc_status_data() or {}, ("status", "staged")) is not None


def _has_rollback_deployment() -> bool:
    return nested_get(_bootc_status_data() or {}, ("status", "rollback")) is not None


def _bootc_image_timestamp(section: str) -> str | None:
    # Query through the compatibility status function so existing cache/test
    # injection remains effective.
    data = _bootc_status_data() or {}
    deployment = nested_get(data, ("status", section)) or {}
    from datetime import datetime

    for path in (("image", "timestamp"), ("timestamp",)):
        value = nested_get(deployment, path)
        if isinstance(value, str) and value.strip():
            try:
                parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00")).astimezone()
                return parsed.strftime("%Y-%m-%d %H:%M %Z")
            except (ValueError, OverflowError):
                return value.strip()
    return None


def _bootc_image_digest(section: str) -> tuple[str, str] | None:
    value = image_digest_from_status(_bootc_status_data(), section)
    return None if value is None else (value[7:19], value[7:])
