"""Qt workers for registry / firmware / flatpak update checks."""
from __future__ import annotations

import json
import logging
from kyth_welcome.services.command import run_sync

from kyth_shared.update_status import read_update_snapshot
from kyth_shared.runtime_output import count_fwupd_updates

from ...qt import Signal
from ..bootc import REGISTRY, bootc_image_digest, bootc_status_data, current_branch
from ..process import run_command
from ..registry import check_registry_update, image_annotations, image_revision
from ..runtime import TrackedThread
from ..updates import UpdateProbeResult

_logger = logging.getLogger(__name__)

_BOOTED_ANNOTATIONS_CACHE: dict[str, dict] = {}


class UpdateCheckWorker(TrackedThread):
    """Compare local booted digest to remote manifest via skopeo inspect."""
    result = Signal(object)

    def __init__(self, *, use_cached_snapshot: bool = True):
        super().__init__()
        self._use_cached_snapshot = use_cached_snapshot

    def run(self):
        try:
            if self._use_cached_snapshot:
                snapshot = read_update_snapshot(max_age=300)
                if snapshot is not None and snapshot.system_state != "unknown":
                    # Validate snapshot freshness against current booted digest;
                    # a stale snapshot (e.g. booted image changed or snapshot
                    # was written before the registry moved) would make the Hub
                    # say "no updates" when an update is actually available.
                    try:
                        cur_digest = None
                        data = bootc_status_data()
                        if data is not None:
                            from kyth_shared.system.bootc_query import image_digest_from_status

                            cur_digest = image_digest_from_status(data, "booted")
                        snap_digest = getattr(snapshot, "booted_digest", "")
                        if (
                            isinstance(snap_digest, str)
                            and snap_digest
                            and isinstance(cur_digest, str)
                            and cur_digest
                            and snap_digest != cur_digest
                        ):
                            raise ValueError("booted digest changed since snapshot")
                    except Exception:  # nosec B110 -- best-effort, failure here is non-fatal by design
                        pass
                    else:
                        self.result.emit(UpdateProbeResult.success("system", snapshot.system_state))
                        return
            result = check_registry_update(
                status_data=bootc_status_data() or {},
                branch=current_branch() or "latest",
                registry=REGISTRY,
            )
            manifest_raw = result.manifest_raw.decode("utf-8", errors="ignore")
            if result.state == "error":
                self.result.emit(UpdateProbeResult.error("system", result.detail))
            else:
                self.result.emit(
                    UpdateProbeResult.success(
                        "system", result.state, detail=result.detail, manifest_raw=manifest_raw,
                    )
                )
        except Exception as exc:
            _logger.warning("System update probe failed: %s", exc)
            self.result.emit(UpdateProbeResult.error("system", str(exc)))


class FirmwareCheckWorker(TrackedThread):
    """Query fwupd for pending firmware updates (non-blocking)."""
    result = Signal(object)

    def run(self):
        try:
            # Shared single source for fwupd commands + count parser.
            from kyth_shared.system.firmware import firmware_refresh_commands, firmware_updates_command
            from kyth_welcome.services.process import run_command as _run

            refresh_cmds = firmware_refresh_commands()
            updates_cmd = firmware_updates_command()
            # Refresh is optional — mirrors watcher.
            if refresh_cmds:
                _run(refresh_cmds[0], timeout=30)
            updates = _run(updates_cmd, timeout=20)
            if updates is None:
                self.result.emit(UpdateProbeResult.error("firmware", "fwupd not available."))
                return
            if updates.returncode == 2 or not updates.stdout.strip():
                self.result.emit(UpdateProbeResult.success("firmware"))
                return
            if updates.returncode != 0:
                self.result.emit(
                    UpdateProbeResult.error(
                        "firmware", updates.stdout.strip() or " ".join(firmware_updates_command()) + " failed.",
                    )
                )
                return
            # Use shared parser — single source for Device ID: counting.
            from kyth_shared.runtime_output import count_fwupd_updates as _count

            count = _count(updates.stdout)
            if count == 0:
                self.result.emit(
                    UpdateProbeResult.error(
                        "firmware", " ".join(firmware_updates_command()) + " output did not contain a recognizable update.",
                    )
                )
                return
            self.result.emit(
                UpdateProbeResult.success("firmware", count, detail=updates.stdout.strip())
            )
        except Exception as exc:
            _logger.warning("Firmware update probe failed: %s", exc)
            self.result.emit(UpdateProbeResult.error("firmware", str(exc)))


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
            annotations = image_annotations(json.loads(r.stdout))
            if "@sha256:" in ref:
                _BOOTED_ANNOTATIONS_CACHE[ref] = annotations
            return annotations
        except Exception:
            return {}

    def run(self):
        tag = current_branch() or "latest"
        booted_digest = bootc_image_digest("booted")
        booted_rev = ""
        if booted_digest:
            ann = self._fetch_annotations(f"{REGISTRY}@{booted_digest[1]}")
            booted_rev = image_revision(ann)

        remote_ann = {}
        if self._remote_manifest:
            try:
                remote_ann = image_annotations(json.loads(self._remote_manifest))
            except Exception:
                _logger.debug("ChangelogWorker.run: parsing the cached remote manifest failed", exc_info=True)

        if not remote_ann:
            remote_ann = self._fetch_annotations(f"{REGISTRY}:{tag}")

        remote_rev = image_revision(remote_ann)
        self.result.emit(booted_rev, remote_rev)


class FlatpakCheckWorker(TrackedThread):
    """Query flatpak for pending system and user updates (uses probe cache)."""
    result = Signal(object)

    def run(self):
        from ..flatpak import _pending_flatpak_update_count

        try:
            count = _pending_flatpak_update_count()
            self.result.emit(
                UpdateProbeResult.success("flatpak", 0 if count is None else int(count))
            )
        except Exception as exc:
            _logger.warning("Flatpak update probe failed: %s", exc)
            self.result.emit(UpdateProbeResult.error("flatpak", str(exc)))
