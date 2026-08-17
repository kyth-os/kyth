"""Single recovery truth — staged / rollback / quarantine in one view.

Repair page previously asked three places:
  * `bootc.has_staged_update()` / `has_rollback_deployment()` (bootc_status, cached 5s)
  * `update_status.UpdateSnapshot.staged` (watcher JSON, 300s)
  * `boot_health.BootHealthState.quarantined` + `quarantine_reason()` (digest quarantine)

This module is the only place that merges them into a terminal Hub banner.
Presentation stays in `page_repair*`, logic stays here so `bootc rollback`
and `clear-quarantine --digest` retry commands are never out of sync.
"""

from __future__ import annotations
import logging

from dataclasses import dataclass

from kyth_shared.boot_health import read_state as read_boot_health, quarantine_reason
from kyth_shared.system.bootc import has_rollback_deployment, has_staged_update
from kyth_shared.update_status import read_update_snapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RecoveryStatus:
    has_staged: bool = False
    has_rollback: bool = False
    quarantined_digest: str = ""
    quarantine_detail: str = ""
    watcher_staged: bool = False
    # Ready-to-paste retry for Hub banner
    clear_quarantine_cmd: str = ""


# S2: truth table central — staged × rollback × quarantined → banner/retry
# staged | rollback | quarant. | banner
#   0        0        0        | up-to-date
#   1        *        0        | reboot to apply staged
#   *        1        0        | rollback available
#   *        *        1        | quarantined — clear-quarantine retry
RECOVERY_BANNER: dict[tuple[bool, bool, bool], str] = {
    (False, False, False): "up-to-date",
    (True, False, False): "reboot to apply staged",
    (True, True, False): "reboot to apply staged",
    (False, True, False): "rollback available",
    (False, False, True): "quarantined — clear-quarantine retry",
    (True, False, True): "quarantined — clear-quarantine retry",
    (True, True, True): "quarantined — clear-quarantine retry",
    (False, True, True): "quarantined — clear-quarantine retry",
}


def recovery_banner(status: RecoveryStatus) -> str:
    return RECOVERY_BANNER[(bool(status.has_staged), bool(status.has_rollback), bool(status.quarantined_digest))]


def get_recovery_status() -> RecoveryStatus:
    try:
        has_staged = bool(has_staged_update())
    except Exception:
        has_staged = False
    try:
        has_rollback = bool(has_rollback_deployment())
    except Exception:
        has_rollback = False

    quarantined = ""
    detail = ""
    clear_cmd = ""
    try:
        state = read_boot_health()
        # surface the most recent quarantined digest if any
        if state.quarantined:
            # pick newest by last_failed_at
            newest = max(state.quarantined.values(), key=lambda r: r.last_failed_at)
            quarantined = newest.digest
            detail = quarantine_reason(state, newest.digest) or newest.reason
            if quarantined:
                clear_cmd = f"sudo kyth-boot-health clear-quarantine --digest {quarantined}"
    except Exception:
        logger.debug("handled expected exception", exc_info=True)
        pass

    try:
        snap = read_update_snapshot(max_age=600)
        watcher_staged = bool(snap and snap.staged_digest)
    except Exception:
        watcher_staged = False

    return RecoveryStatus(
        has_staged=has_staged or watcher_staged,
        has_rollback=has_rollback,
        quarantined_digest=quarantined,
        quarantine_detail=detail,
        watcher_staged=watcher_staged,
        clear_quarantine_cmd=clear_cmd,
    )
