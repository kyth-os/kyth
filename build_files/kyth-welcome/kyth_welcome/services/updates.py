import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable


InspectRunner = Callable[[str], subprocess.CompletedProcess[bytes]]


@dataclass(frozen=True)
class UpdateCheckResult:
    state: str
    detail: str = ""


def nested_get(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def booted_image_digest(status_data: dict[str, Any]) -> str | None:
    booted = nested_get(status_data, ("status", "booted")) or {}
    for path in (
        ("image", "imageDigest"),
        ("image", "digest"),
        ("imageDigest",),
        ("digest",),
    ):
        value = nested_get(booted, path)
        if isinstance(value, str) and value.startswith("sha256:"):
            return value
    return None


def default_inspect_runner(ref: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["skopeo", "inspect", "--raw", "--no-creds", f"docker://{ref}"],
        capture_output=True,
        timeout=45,
    )


def _remote_digest_and_timestamp(raw: bytes) -> tuple[str | None, str]:
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
        remote_digest, remote_ts = _remote_digest_and_timestamp(result.stdout)
    except Exception:
        remote_digest, remote_ts = None, ""

    if remote_digest is None:
        remote_digest = "sha256:" + hashlib.sha256(result.stdout).hexdigest()

    if remote_digest == local_digest:
        return UpdateCheckResult("uptodate", remote_ts)
    return UpdateCheckResult("available", remote_ts)


def firmware_check_commands(refresh: bool = True) -> list[list[str]]:
    commands: list[list[str]] = []
    if refresh:
        commands.append(["fwupdmgr", "refresh", "--force"])
    commands.append(["fwupdmgr", "get-updates"])
    return commands
