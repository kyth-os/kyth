"""bootc status, image reference, branch, and deployment helpers.

Pure stdlib — safe to import from CLI tools (update-watcher) without Qt.
"""
from __future__ import annotations

from kyth_shared.system.bootc import (
    REGISTRY,
    BranchCardView,
    BranchesView,
    UpdateAvailabilityView,
    _active_bootc_operation,
    _bootc_cancel_block_reason,
    _bootc_image_digest,
    _bootc_image_reference,
    _bootc_image_timestamp,
    _bootc_proxy_running,
    _bootc_status_data,
    _bootc_status_text,
    _branch_display_name,
    _branch_from_ref,
    _current_branch,
    _current_kernel_flavor,
    _default_phase,
    _fetch_bootc_status_data,
    _fetch_bootc_status_text,
    _has_rollback_deployment,
    _has_staged_update,
    _image_tag_for_channel,
    _image_tag_for_kernel,
    _nested_get,
    _parse_update_phase,
    _walk_strings,
    branches_view,
    fetch_bootc_status_data_uncached,
    image_digest_from_status,
    image_reference_from_status,
    nested_get,
    update_availability_view,
    walk_strings,
)
