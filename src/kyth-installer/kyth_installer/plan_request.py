"""Pure request normalization for installer planning."""

from __future__ import annotations

from dataclasses import replace

from .context import InstallationState, InstallRequest
from .disk import _normal_device_path
from .plan_types import InstallPlan


def as_request(state: InstallationState | InstallRequest) -> InstallRequest:
    """Coerce the HTTP state dictionary to the immutable request boundary."""
    if isinstance(state, InstallRequest):
        return state
    return InstallRequest.from_state(state)


def normalized_install_mode(state: InstallationState | InstallRequest) -> str:
    """Return the canonical storage-mode spelling used by planning."""
    request = as_request(state)
    return str(request.install_mode or "wipe").strip().lower() or "wipe"


def install_plan_from_state(state: InstallationState | InstallRequest) -> InstallPlan:
    """Build the storage-only plan projection from an install request."""
    request = as_request(state)
    return InstallPlan(
        mode=normalized_install_mode(request),
        disk=_normal_device_path(request.disk),
        target_partition=_normal_device_path(request.target_partition),
    )


def request_with_install_plan(
    state: InstallationState | InstallRequest,
    plan: InstallPlan,
) -> InstallRequest:
    """Return immutable request input updated with resolved storage fields."""
    request = as_request(state)
    changes = {"install_mode": plan.mode}
    if plan.disk is not None:
        changes["disk"] = plan.disk
    if plan.target_partition is not None:
        changes["target_partition"] = plan.target_partition
    return replace(request, **changes)
