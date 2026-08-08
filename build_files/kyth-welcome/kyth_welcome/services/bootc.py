"""bootc status, image reference, branch, and deployment helpers.

Pure stdlib — safe to import from CLI tools (update-watcher) without Qt.
"""
from __future__ import annotations

# pylint: disable=unused-import
from kyth_shared.system.bootc import (  # noqa: F401 — re-export pure API for existing imports
    REGISTRY,
    BranchCardView,
    BranchesView,
    UpdateAvailabilityView,
    active_bootc_operation,
    bootc_cancel_block_reason,
    bootc_image_digest,
    bootc_image_reference,
    bootc_image_timestamp,
    bootc_proxy_running,
    bootc_status_data,
    bootc_status_text,
    branch_display_name,
    branch_from_ref,
    branches_view,
    current_branch,
    current_kernel_flavor,
    default_phase,
    fetch_bootc_status_data,
    fetch_bootc_status_data_uncached,
    fetch_bootc_status_text,
    has_rollback_deployment,
    has_staged_update,
    image_digest_from_status,
    image_reference_from_status,
    image_tag_for_channel,
    image_tag_for_kernel,
    nested_get,
    parse_update_phase,
    update_availability_view,
    walk_strings,
)
# pylint: enable=unused-import
