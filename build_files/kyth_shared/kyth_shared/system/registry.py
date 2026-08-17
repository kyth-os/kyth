"""Registry / skopeo helpers for comparing local bootc digests to remote images.

Pure stdlib — shared by System Hub update checks and kyth-update-watcher.
"""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess

from ..commands import run as run_command
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from kyth_shared.system.bootc_query import image_digest_from_status, nested_get

logger = logging.getLogger(__name__)

InspectRunner = Callable[[str], subprocess.CompletedProcess[bytes]]

_REVISION_KEY = "org.opencontainers.image.revision"


@dataclass(frozen=True)
class UpdateCheckResult:
    state: str
    detail: str = ""
    manifest_raw: bytes = b""


def booted_image_digest(status_data: dict[str, Any]) -> str | None:
    return image_digest_from_status(status_data, "booted")


def amd64_manifest_entry(manifest: dict[str, Any]) -> dict[str, Any] | None:
    """Return the ``amd64``/``linux`` entry from an OCI image index, or None.

    None is returned both when the manifest is not a multi-arch index and when
    the index carries no matching entry; callers that need to distinguish those
    cases should guard on ``manifest.get("manifests")`` themselves.
    """
    manifests = manifest.get("manifests")
    if not isinstance(manifests, list):
        return None
    for entry in manifests:
        plat = entry.get("platform", {})
        if plat.get("architecture") == "amd64" and plat.get("os") == "linux":
            return entry
    return None


def image_annotations(manifest: dict[str, Any]) -> dict[str, Any]:
    """Annotations for the amd64 image.

    Prefers the index's top-level annotations and falls back to the platform
    entry's annotations only when the top level carries no image revision.
    """
    annotations = manifest.get("annotations") or {}
    if not annotations.get(_REVISION_KEY):
        entry = amd64_manifest_entry(manifest)
        if entry is not None:
            annotations = entry.get("annotations") or annotations
    return annotations


def image_revision(annotations: dict[str, Any]) -> str:
    """Short (12-char) image revision from an annotations dict."""
    return annotations.get(_REVISION_KEY, "")[:12]


def default_inspect_runner(ref: str) -> subprocess.CompletedProcess[bytes]:
    return run_command(
        ["skopeo", "inspect", "--raw", "--no-creds", f"docker://{ref}"],
        capture_output=True,
        timeout=10,
        check=False,
    )


def remote_digest_and_timestamp(raw: bytes) -> tuple[str | None, str]:
    """Parse a raw OCI manifest/index and return (digest, created_ts)."""
    manifest = json.loads(raw)
    remote_digest: str | None = None
    remote_ts = ""

    annotations = manifest.get("annotations") or {}
    raw_ts = annotations.get("org.opencontainers.image.created", "")
    if raw_ts:
        try:
            dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).astimezone()
            remote_ts = dt.strftime("%Y-%m-%d %H:%M %Z")
        except ValueError:
            remote_ts = ""

    if manifest.get("mediaType", "").endswith("manifest.v1+json"):
        remote_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    elif isinstance(manifest.get("manifests"), list):
        entry = amd64_manifest_entry(manifest)
        digest = entry.get("digest") if entry is not None else None
        if isinstance(digest, str) and digest.startswith("sha256:"):
            remote_digest = digest
    elif manifest.get("config") and manifest.get("layers"):
        remote_digest = "sha256:" + hashlib.sha256(raw).hexdigest()

    return remote_digest, remote_ts


_remote_digest_and_timestamp = remote_digest_and_timestamp


def remote_digest_for_ref(
    ref: str,
    *,
    inspect_runner: InspectRunner = default_inspect_runner,
    timeout_note: str | None = None,
) -> str | None:
    try:
        result = inspect_runner(ref)
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        logger.debug("handled expected exception", exc_info=True)
        return None
    if result.returncode != 0:
        return None
    try:
        remote_digest, _ = remote_digest_and_timestamp(result.stdout)
    except (OSError, ValueError, AttributeError, KeyError, json.JSONDecodeError, UnicodeError):
        logger.debug("handled expected exception", exc_info=True)
        remote_digest = None
    if remote_digest is None:
        # Unknown manifest type — don't fabricate a digest that would falsely
        # appear as "available" and re-stage every watcher cycle.
        return None
    return remote_digest


def check_registry_update(
    *,
    status_data: dict[str, Any],
    branch: str,
    registry: str,
    inspect_runner: InspectRunner = default_inspect_runner,
) -> UpdateCheckResult:
    local_digest = booted_image_digest(status_data)
    if not local_digest:
        return UpdateCheckResult("error", "Could not read the current booted image digest.")

    ref = f"{registry}:{branch}"
    try:
        result = inspect_runner(ref)
    except FileNotFoundError:
        logger.debug("handled expected exception", exc_info=True)
        return UpdateCheckResult("error", "skopeo is not installed.")
    except subprocess.TimeoutExpired:
        logger.debug("handled expected exception", exc_info=True)
        return UpdateCheckResult("error", f"Timed out checking {ref}.")
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError) as exc:
        logger.debug("handled expected exception", exc_info=True)
        return UpdateCheckResult("error", f"Could not check {ref}: {exc}")

    if result.returncode != 0:
        stderr = (result.stderr or b"").decode(errors="replace").strip()
        return UpdateCheckResult("error", stderr or f"Could not check {ref}.")

    try:
        remote_digest, remote_ts = remote_digest_and_timestamp(result.stdout)
    except (OSError, ValueError, AttributeError, KeyError, json.JSONDecodeError, UnicodeError) as exc:
        logger.debug("handled expected exception", exc_info=True)
        remote_digest, remote_ts = None, ""

    if remote_digest is None:
        return UpdateCheckResult("error", f"Could not parse manifest for {ref}.")

    if remote_digest == local_digest:
        return UpdateCheckResult("uptodate", remote_ts, result.stdout)
    return UpdateCheckResult("available", remote_ts, result.stdout)


__all__ = [
    "InspectRunner",
    "UpdateCheckResult",
    "amd64_manifest_entry",
    "booted_image_digest",
    "check_registry_update",
    "default_inspect_runner",
    "image_annotations",
    "image_revision",
    "nested_get",
    "remote_digest_and_timestamp",
    "remote_digest_for_ref",
]
