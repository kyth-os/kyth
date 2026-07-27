"""bootc status, image reference, branch, and deployment helpers.

Pure stdlib — safe to import from CLI tools (update-watcher) without Qt.

Thin, cache-aware wrappers around ``bootc_query``/``bootc_policy``. Pure
pass-throughs of an already-public policy/query function (no added logic)
aren't re-defined here — import them from ``bootc_policy``/``bootc_query``
(also re-exported below) directly.
"""
from __future__ import annotations

from ..commands import run as run_command
from kyth_shared.system.process import BOOTC_CACHE_TTL, command_stdout, probe_cached
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
    image_tag_for_channel as _raw_image_tag_for_channel,
    image_tag_for_kernel as _raw_image_tag_for_kernel,
    parse_update_phase,
    update_availability_view,
)

nested_get = query.nested_get
walk_strings = query.walk_strings
image_reference_from_status = query.image_reference_from_status
image_digest_from_status = query.image_digest_from_status


def fetch_bootc_status_text() -> str:
    return query.fetch_status_text()


def bootc_status_text() -> str:
    # Keep patchable compatibility boundaries used by probes and tests.
    return probe_cached("bootc-status-text", BOOTC_CACHE_TTL, fetch_bootc_status_text)


def fetch_bootc_status_data() -> dict | None:
    return query.fetch_status_data()


def bootc_status_data() -> dict | None:
    return probe_cached("bootc-status-data", BOOTC_CACHE_TTL, fetch_bootc_status_data)


def fetch_bootc_status_data_uncached() -> dict | None:
    return fetch_bootc_status_data()


def active_bootc_operation() -> str | None:
    return query.active_operation()


def bootc_proxy_running() -> bool:
    try:
        result = run_command(
            ["pgrep", "-f", "skopeo.*image-proxy"],
            capture_output=True, timeout=2, check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def bootc_cancel_block_reason(mode: str, phase: str) -> str:
    return cancel_block_reason(mode, phase)


def bootc_image_reference() -> str | None:
    data = bootc_status_data() or {}
    ref = query.image_reference_from_status(data)
    if ref:
        return ref
    ref = query.image_reference_from_status(data, status_output=bootc_status_text())
    if ref:
        return ref
    # Preserve the compatibility module's patchable status seams while
    # delegating the fallback query to the query adapter.
    return query.image_reference()


def current_branch() -> str | None:
    return probe_cached(
        "bootc-branch", BOOTC_CACHE_TTL,
        lambda: branch_from_ref(bootc_image_reference()),
    )


def current_kernel_flavor() -> str:
    def fetch() -> str:
        try:
            with open("/usr/share/kyth/kernel-flavor") as fh:
                flavor = fh.read().strip().lower()
                if flavor in {"fedora", "cachy"}:
                    return flavor
        except OSError:
            pass
        return "cachy" if "cachy" in command_stdout(["uname", "-r"]).lower() else "fedora"

    return probe_cached("kernel-flavor", 60.0, fetch)


def image_tag_for_channel(channel: str, flavor: str | None = None) -> str:
    return _raw_image_tag_for_channel(channel, flavor or current_kernel_flavor())


def image_tag_for_kernel(flavor: str) -> str:
    return _raw_image_tag_for_kernel(flavor, current_branch())


def has_staged_update() -> bool:
    return nested_get(bootc_status_data() or {}, ("status", "staged")) is not None


def has_rollback_deployment() -> bool:
    return nested_get(bootc_status_data() or {}, ("status", "rollback")) is not None


def bootc_image_timestamp(section: str) -> str | None:
    # Query through the compatibility status function so existing cache/test
    # injection remains effective.
    data = bootc_status_data() or {}
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


def bootc_image_digest(section: str) -> tuple[str, str] | None:
    value = image_digest_from_status(bootc_status_data(), section)
    return None if value is None else (value[7:19], value[7:])
