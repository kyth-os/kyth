"""Registry / skopeo helpers for comparing local bootc digests to remote images.

Pure stdlib — shared by System Hub update checks and kyth-update-watcher.
"""
from __future__ import annotations

# pylint: disable=unused-import
from kyth_shared.system.registry import (  # noqa: F401 — re-export pure API for existing imports
    InspectRunner,
    UpdateCheckResult,
    amd64_manifest_entry,
    booted_image_digest,
    check_registry_update,
    default_inspect_runner,
    image_annotations,
    image_revision,
    nested_get,
    remote_digest_and_timestamp,
    remote_digest_for_ref,
)
# pylint: enable=unused-import
