"""Qt workers for registry / firmware / flatpak update checks."""
from __future__ import annotations

import json
import logging
from kyth_welcome.services.command import run_sync

from kyth_shared.update_status import read_update_snapshot

from ...qt import Signal
from ..bootc import REGISTRY, _bootc_image_digest, _bootc_status_data, _current_branch
from ..process import _run_command
from ..registry import check_registry_update
from ..runtime import TrackedThread
from ..updates import firmware_check_commands

_logger = logging.getLogger(__name__)

_BOOTED_ANNOTATIONS_CACHE: dict[str, dict] = {}


class UpdateCheckWorker(TrackedThread):
    """Compare local booted digest to remote manifest via skopeo inspect."""
    result = Signal(str, str, str)

    def run(self):
        snapshot = read_update_snapshot(max_age=300)
        if snapshot is not None and snapshot.system_state != "unknown":
            self.result.emit(snapshot.system_state, "", "")
            return
        result = check_registry_update(
            status_data=_bootc_status_data() or {},
            branch=_current_branch() or "latest",
            registry=REGISTRY,
        )
        self.result.emit(
            result.state,
            result.detail,
            result.manifest_raw.decode("utf-8", errors="ignore"),
        )


class FirmwareCheckWorker(TrackedThread):
    """Query fwupd for pending firmware updates (non-blocking)."""
    result = Signal(int, str)

    def run(self):
        refresh_cmd, updates_cmd = firmware_check_commands(refresh=True)
        _run_command(refresh_cmd, timeout=30)
        updates = _run_command(updates_cmd, timeout=20)
        if updates is None:
            self.result.emit(-1, "fwupd not available.")
            return
        if updates.returncode == 2 or not updates.stdout.strip():
            self.result.emit(0, "")
            return
        if updates.returncode != 0:
            self.result.emit(-1, updates.stdout.strip() or "fwupdmgr get-updates failed.")
            return
        count = max(1, updates.stdout.count("Device ID:"))
        self.result.emit(count, updates.stdout.strip())


class ChangelogWorker(TrackedThread):
    """Fetch OCI revision annotations for booted and remote images."""
    result = Signal(str, str)  # (booted_rev, remote_rev)

    def __init__(self, remote_manifest: str = ""):
        super().__init__()
        self._remote_manifest = remote_manifest

    def _fetch_annotations(self, ref: str) -> dict:
        if "@sha256:" in ref and ref in _BOOTED_ANNOTATIONS_CACHE:
            return _BOOTED_ANNOTATIONS_CACHE[ref]
        try:
            r = run_sync(
                ["skopeo", "inspect", "--raw", "--no-creds", f"docker://{ref}"],
                capture_output=True, timeout=30, check=False,
            )
            if r.returncode != 0:
                return {}
            manifest = json.loads(r.stdout)
            annotations = manifest.get("annotations") or {}
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
                _logger.debug("ChangelogWorker.run: parsing the cached remote manifest failed", exc_info=True)

        if not remote_ann:
            remote_ann = self._fetch_annotations(f"{REGISTRY}:{tag}")

        remote_rev = remote_ann.get("org.opencontainers.image.revision", "")[:12]
        self.result.emit(booted_rev, remote_rev)


class FlatpakCheckWorker(TrackedThread):
    """Query flatpak for pending system and user updates (uses probe cache)."""
    result = Signal(int)

    def run(self):
        from ..flatpak import _pending_flatpak_update_count

        count = _pending_flatpak_update_count()
        self.result.emit(0 if count is None else int(count))
