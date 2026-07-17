"""Update-check workers (Qt) built on pure registry/bootc helpers."""
from __future__ import annotations

import json
import subprocess
from typing import Any

from ..qt import Signal
from .bootc import REGISTRY, _bootc_image_digest, _bootc_status_data, _current_branch
from .process import _run_command
from .registry import (  # noqa: F401 — re-export pure API for existing imports
    InspectRunner,
    UpdateCheckResult,
    booted_image_digest,
    check_registry_update,
    default_inspect_runner,
    nested_get,
    remote_digest_and_timestamp,
)
from .runtime import TrackedThread

_BOOTED_ANNOTATIONS_CACHE: dict[str, dict] = {}


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
