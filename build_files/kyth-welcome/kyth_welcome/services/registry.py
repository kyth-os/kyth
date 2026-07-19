"""Registry / skopeo helpers for comparing local bootc digests to remote images.

Pure stdlib — shared by System Hub update checks and kyth-update-watcher.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from .bootc import image_digest_from_status, nested_get

InspectRunner = Callable[[str], subprocess.CompletedProcess[bytes]]


@dataclass(frozen=True)
class UpdateCheckResult:
    state: str
    detail: str = ""
    manifest_raw: bytes = b""


def booted_image_digest(status_data: dict[str, Any]) -> str | None:
    return image_digest_from_status(status_data, "booted")


def default_inspect_runner(ref: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["skopeo", "inspect", "--raw", "--no-creds", f"docker://{ref}"],
        capture_output=True,
        timeout=45,
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
    else:
        manifests = manifest.get("manifests")
        if isinstance(manifests, list):
            for entry in manifests:
                plat = entry.get("platform", {})
                digest = entry.get("digest")
                if (
                    plat.get("architecture") == "amd64"
                    and plat.get("os") == "linux"
                    and isinstance(digest, str)
                    and digest.startswith("sha256:")
                ):
                    remote_digest = digest
                    break
        elif manifest.get("config") and manifest.get("layers"):
            remote_digest = "sha256:" + hashlib.sha256(raw).hexdigest()

    return remote_digest, remote_ts


# Private alias used by older call sites
_remote_digest_and_timestamp = remote_digest_and_timestamp


def remote_digest_for_ref(
    ref: str,
    *,
    inspect_runner: InspectRunner = default_inspect_runner,
    timeout_note: str | None = None,
) -> str | None:
    """Return remote ``sha256:…`` for *ref*, or None on failure.

    *ref* may be ``registry/name:tag`` (docker transport is added).
    """
    try:
        result = inspect_runner(ref)
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return None
    if result.returncode != 0:
        return None
    try:
        remote_digest, _ = remote_digest_and_timestamp(result.stdout)
    except Exception:
        remote_digest = None
    if remote_digest is None:
        remote_digest = "sha256:" + hashlib.sha256(result.stdout).hexdigest()
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
        return UpdateCheckResult("error", "skopeo is not installed.")
    except subprocess.TimeoutExpired:
        return UpdateCheckResult("error", f"Timed out checking {ref}.")
    except Exception:
        return UpdateCheckResult("error", f"Could not check {ref}.")

    if result.returncode != 0:
        stderr = (result.stderr or b"").decode(errors="replace").strip()
        return UpdateCheckResult("error", stderr or f"Could not check {ref}.")

    try:
        remote_digest, remote_ts = remote_digest_and_timestamp(result.stdout)
    except Exception:
        remote_digest, remote_ts = None, ""

    if remote_digest is None:
        remote_digest = "sha256:" + hashlib.sha256(result.stdout).hexdigest()

    if remote_digest == local_digest:
        return UpdateCheckResult("uptodate", remote_ts, result.stdout)
    return UpdateCheckResult("available", remote_ts, result.stdout)


# Re-export nested_get for callers that previously used updates.nested_get
__all__ = [
    "InspectRunner",
    "UpdateCheckResult",
    "booted_image_digest",
    "check_registry_update",
    "default_inspect_runner",
    "nested_get",
    "remote_digest_and_timestamp",
    "remote_digest_for_ref",
]
