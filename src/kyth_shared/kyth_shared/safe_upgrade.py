"""Guard manual bootc upgrades with rollout and digest-quarantine policy."""
from __future__ import annotations
import json
import logging
import subprocess

import os
import sys
import tomllib
from pathlib import Path
from typing import Sequence

from .boot_health import (
    DEFAULT_STATE_PATH,
    image_ring,
    quarantine_reason,
    rollout_policy_reason,
)

# Progressive: Hub control-plane hook — record staged state for RepairPage
# so UpdatePage and RepairPage share one source without per-page bootc spawns
try:
    from kyth_welcome.services.hub_state import HUB_STATE as _HUB_STATE  # type: ignore[import-not-found]
except (ImportError, OSError, subprocess.SubprocessError) as exc:  # noqa: BLE001 -- narrow: hub_state optional import
    _HUB_STATE = None  # type: ignore[assignment]
from .commands import run
from .system.bootc import image_digest_from_status, image_reference_from_status
from .system.bootc_query import fetch_status_data
from .system.registry import remote_digest_for_ref

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("/etc/kyth/auto-update.toml")


def load_rollout_ring(path: str | Path = DEFAULT_CONFIG_PATH) -> str:
    try:
        with Path(path).open("rb") as stream:
            data = tomllib.load(stream)
        section = data.get("auto_update", {})
        return str(section.get("rollout_ring", "follow-image"))
    except (OSError, TypeError, ValueError, tomllib.TOMLDecodeError):
        return "follow-image"


def upgrade(
    *,
    state_path: str | Path = DEFAULT_STATE_PATH,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> int:
    if os.geteuid() != 0:
        print("kyth-safe-upgrade must run as root", file=sys.stderr)
        return 77
    status = fetch_status_data()
    reference = image_reference_from_status(status)
    if not reference:
        print("Could not determine the booted image reference", file=sys.stderr)
        return 2
    ring = load_rollout_ring(config_path)
    policy_reason = rollout_policy_reason(reference, ring)
    if policy_reason:
        print(f"Update blocked by rollout policy: {policy_reason}", file=sys.stderr)
        return 3
    remote_digest = remote_digest_for_ref(reference)
    if not remote_digest:
        print("Could not resolve the remote image digest; update not staged", file=sys.stderr)
        return 4
    # Use UpdateCoordinator to avoid lost-update race with concurrent Hub/greenboot
    from .update_coordinator import UpdateCoordinator

    coord = UpdateCoordinator(state_path)
    state = coord.read()
    blocked = quarantine_reason(state, remote_digest)
    if blocked:
        print(f"Update blocked: {blocked}", file=sys.stderr)
        print(
            f"To retry deliberately: sudo kyth-boot-health clear-quarantine --digest {remote_digest}",
            file=sys.stderr,
        )
        return 5
    staged = image_digest_from_status(status, "staged")
    booted = image_digest_from_status(status, "booted")
    if remote_digest in {staged, booted}:
        print("KythOS is already running or has staged the latest allowed digest")
        return 0
    # Pre-flight: require ~2 GB free on /sysroot (bootc needs space for new
    # deployment). Must not check "/" — on composefs-root systems (Fedora
    # 44+) / is a tiny synthetic overlay that always reports ~0 bytes free,
    # which made this check fail unconditionally regardless of real free
    # space on the underlying /sysroot partition.
    try:
        import shutil

        free = shutil.disk_usage("/sysroot").free
        need = 2 * 1024**3
        if free < need:
            print(f"Not enough free disk space: {free // (1024**2)} MB free, need {need // (1024**2)} MB — free space and retry", file=sys.stderr)
            _maybe_trigger_guardian()
            return 6
    except (OSError, AttributeError, ValueError):  # noqa: BLE001 -- narrow: best-effort production path
        pass
    # Concurrency: if another bootc upgrade is in progress, retry later
    try:
        import fcntl  # noqa: PLC0415 -- local import keeps non-Linux tests portable

        lock_path = Path("/run/kyth-bootc.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        _lock_fh = open(lock_path, "a+")  # noqa: SIM115, PTH123 -- intentional persistent fd for flock lifetime
        try:
            fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another bootc upgrade is in progress — will retry on next run", file=sys.stderr)
            _maybe_trigger_guardian()
            return 6
        # Hold lock for duration of upgrade; released on process exit
    except (OSError, ImportError, AttributeError):  # noqa: BLE001 -- narrow: best-effort production path
        pass
    try:
        result = run(["bootc", "upgrade"], check=False, timeout=1800)
    except subprocess.TimeoutExpired as exc:
        print(f"bootc upgrade timed out after {exc.timeout}s — will retry on next run (not quarantined)", file=sys.stderr)
        _maybe_trigger_guardian()
        return 6
    except (FileNotFoundError, OSError) as exc:
        # `run` wraps subprocess.run — on hosts without bootc (e.g. testbeds,
        # wazuh nodes, or non-immutable dev VMs) the binary is missing and
        # would previously surface as a traceback / exit 1. Surface a clear
        # message and the conventional 127 (command not found) instead.
        if isinstance(exc, FileNotFoundError) or "No such file" in str(exc):
            print("bootc is not installed — cannot stage an update on this system", file=sys.stderr)
            print("On KythOS this is /usr/bin/bootc (from the bootc package). On a non-immutable host, install bootc first.", file=sys.stderr)
        else:
            print(f"Could not execute bootc: {exc}", file=sys.stderr)
        return 127
    if result.returncode:
        # If bootc reported failure but actually staged the digest (e.g. pull
        # completed before post-pull hook failed), treat as staged so we don't
        # force a retryable loop. Otherwise surface retryable pull hint.
        try:
            staged_after = image_digest_from_status(fetch_status_data(), "staged")
            if staged_after == remote_digest:
                pass  # fall through to record_staged success path
            else:
                return result.returncode
        except (OSError, ValueError, TypeError, AttributeError, KeyError, json.JSONDecodeError):  # noqa: BLE001 -- narrow: best-effort production path
            return result.returncode
    try:
        coord.record_staged(remote_digest, rollout_ring=image_ring(reference) or ring)
    except ValueError as exc:
        print(f"Refusing to persist corrupt boot health state: {exc}", file=sys.stderr)
        return 1
    # Control-plane: surface staged digest to Hub without per-page bootc spawns.
    if _HUB_STATE is not None:
        try:
            _HUB_STATE.set_update_status("staged", remote_digest)
            _HUB_STATE.set("staged_digest", remote_digest)
            # Keep rollback_available in sync so RepairPage can offer one-click rollback
            try:
                from .system.bootc import has_rollback_deployment

                _HUB_STATE.set_rollback_available(bool(has_rollback_deployment()))
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                logger.debug("handled expected exception", exc_info=True)
                pass
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
            pass
    return 0


def _maybe_trigger_guardian() -> None:
    """Touch probe-cache so kyth-guardian.path fires on next user session.

    Keeps privilege boundary: safe_upgrade (root) never calls Guardian directly,
    it just pokes the file the user path unit already watches.
    """
    try:
        # XDG_RUNTIME_DIR is /run/user/<uid> for the graphical session; try common uid
        for uid in ("1000",):
            p = Path(f"/run/user/{uid}/kyth/probe-cache.json")
            if p.parent.exists():
                p.touch(exist_ok=True)
                return
        # Fallback: touch the system probe cache location
        Path("/var/cache/kyth/probe-cache.json").touch(exist_ok=True)
    except (OSError, ValueError, AttributeError):
        pass


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        print("kyth-safe-upgrade accepts no arguments", file=sys.stderr)
        return 64
    return upgrade()


if __name__ == "__main__":
    raise SystemExit(main())