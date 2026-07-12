import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ..qt import Signal
from ..core_base import (
    TrackedThread,
    _bootc_status_data,
    _current_branch,
    _bootc_image_digest,
    REGISTRY,
    _run_command,
)


InspectRunner = Callable[[str], subprocess.CompletedProcess[bytes]]


@dataclass(frozen=True)
class UpdateCheckResult:
    state: str
    detail: str = ""
    manifest_raw: bytes = b""


_BOOTED_ANNOTATIONS_CACHE: dict[str, dict] = {}


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
        return UpdateCheckResult("uptodate", remote_ts, result.stdout)
    return UpdateCheckResult("available", remote_ts, result.stdout)


def firmware_check_commands(refresh: bool = True) -> list[list[str]]:
    commands: list[list[str]] = []
    if refresh:
        commands.append(["fwupdmgr", "refresh"])
    commands.append(["fwupdmgr", "get-updates"])
    return commands


# ── Update check worker ────────────────────────────────────────────────────────
class UpdateCheckWorker(TrackedThread):
    """Checks if a newer image is available in the registry without downloading anything.
    Compares the local booted digest against the remote manifest via skopeo inspect.
    Emits result(state, remote_ts, manifest_raw) where state is 'available', 'uptodate', or 'error'."""
    result = Signal(str, str, str)

    def run(self):
        result = check_registry_update(
            status_data=_bootc_status_data() or {},
            branch=_current_branch() or "latest",
            registry=REGISTRY,
        )
        self.result.emit(
            result.state,
            result.detail,
            result.manifest_raw.decode("utf-8", errors="ignore")
        )


# ── Firmware check worker ──────────────────────────────────────────────────────
class FirmwareCheckWorker(TrackedThread):
    """Query fwupd for pending firmware updates (non-blocking background check).

    Emits result(count, summary) where count is:
      -1  fwupd unavailable or hard error
       0  up to date
       n  number of devices with pending updates
    """
    result = Signal(int, str)

    def run(self):
        refresh_cmd, updates_cmd = firmware_check_commands(refresh=True)
        _run_command(refresh_cmd, timeout=30)
        updates = _run_command(updates_cmd, timeout=20)
        if updates is None:
            self.result.emit(-1, "fwupd not available.")
            return
        if updates.returncode == 2 or not updates.stdout.strip():
            # exit code 2 = nothing to update
            self.result.emit(0, "")
            return
        if updates.returncode != 0:
            self.result.emit(-1, updates.stdout.strip() or "fwupdmgr get-updates failed.")
            return
        count = max(1, updates.stdout.count("Device ID:"))
        self.result.emit(count, updates.stdout.strip())


# ── Changelog worker ───────────────────────────────────────────────────────────
class ChangelogWorker(TrackedThread):
    """Fetches OCI revision annotations for the booted and latest remote images so the
    Update page can show a precise GitHub compare link instead of a generic commits URL."""
    result = Signal(str, str)  # (booted_rev, remote_rev) — short git SHAs, may be empty

    def __init__(self, remote_manifest: str = ""):
        super().__init__()
        self._remote_manifest = remote_manifest

    def _fetch_annotations(self, ref: str) -> dict:
        global _BOOTED_ANNOTATIONS_CACHE
        if "@sha256:" in ref and ref in _BOOTED_ANNOTATIONS_CACHE:
            return _BOOTED_ANNOTATIONS_CACHE[ref]
        try:
            r = subprocess.run(
                ["skopeo", "inspect", "--raw", "--no-creds", f"docker://{ref}"],
                capture_output=True, timeout=30,
            )
            if r.returncode != 0:
                return {}
            manifest = json.loads(r.stdout)
            annotations = manifest.get("annotations") or {}
            # For multi-arch index the interesting annotations are on the amd64 entry.
            if not annotations.get("org.opencontainers.image.revision"):
                for entry in manifest.get("manifests", []):
                    plat = entry.get("platform", {})
                    if plat.get("architecture") == "amd64" and plat.get("os") == "linux":
                        annotations = entry.get("annotations") or annotations
                        break
            if "@sha256:" in ref:
                _BOOTED_ANNOTATIONS_CACHE[ref] = annotations
            return annotations
        except Exception:
            return {}

    def run(self):
        tag = _current_branch() or "latest"
        booted_digest = _bootc_image_digest("booted")
        booted_rev = ""
        if booted_digest:
            ann = self._fetch_annotations(f"{REGISTRY}@{booted_digest[1]}")
            booted_rev = ann.get("org.opencontainers.image.revision", "")[:12]

        remote_ann = {}
        if self._remote_manifest:
            try:
                manifest = json.loads(self._remote_manifest)
                remote_ann = manifest.get("annotations") or {}
                if not remote_ann.get("org.opencontainers.image.revision"):
                    for entry in manifest.get("manifests", []):
                        plat = entry.get("platform", {})
                        if plat.get("architecture") == "amd64" and plat.get("os") == "linux":
                            remote_ann = entry.get("annotations") or remote_ann
                            break
            except Exception:
                pass

        if not remote_ann:
            remote_ann = self._fetch_annotations(f"{REGISTRY}:{tag}")

        remote_rev = remote_ann.get("org.opencontainers.image.revision", "")[:12]
        self.result.emit(booted_rev, remote_rev)


# ── Flatpak check worker ───────────────────────────────────────────────────────
class FlatpakCheckWorker(TrackedThread):
    """Query flatpak for pending updates (both system-wide and user-level).
    Emits result(count)."""
    result = Signal(int)

    def run(self):
        total = 0
        try:
            r = subprocess.run(
                ["flatpak", "remote-ls", "--updates", "--system", "--columns=application"],
                capture_output=True, text=True, timeout=30, check=False,
            )
            if r.returncode == 0:
                total += len([ln for ln in r.stdout.splitlines() if ln.strip()])
        except Exception:
            pass

        try:
            r = subprocess.run(
                ["flatpak", "remote-ls", "--updates", "--user", "--columns=application"],
                capture_output=True, text=True, timeout=30, check=False,
            )
            if r.returncode == 0:
                total += len([ln for ln in r.stdout.splitlines() if ln.strip()])
        except Exception:
            pass

        self.result.emit(total)
