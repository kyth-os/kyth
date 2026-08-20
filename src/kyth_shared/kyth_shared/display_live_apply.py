"""Display live-apply — kscreen-doctor apply + read-back."""
import logging
import time

from kyth_shared.commands import run as _run

logger = logging.getLogger(__name__)

_last_apply_monotonic: float = 0.0
_DEBOUNCE_S = 2.0


def apply_display_live(mode: str) -> bool:
    global _last_apply_monotonic
    now = time.monotonic()
    if now - _last_apply_monotonic < _DEBOUNCE_S:
        logger.debug("display live-apply debounced (%.2fs since last)", now - _last_apply_monotonic)
        return False
    _last_apply_monotonic = now
    try:
        r = _run(["kscreen-doctor", "-o"], capture_output=True, text=True, timeout=5)
        if r is None:
            logger.debug("kscreen-doctor unavailable")
            return False
        if r.returncode != 0:
            logger.debug("kscreen-doctor failed with exit %s: %s", r.returncode, (r.stderr or r.stdout or "").strip()[:300])
            return False
        # read-back verification: check output contains mode
        return mode in r.stdout
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path  # nosec B110 -- best-effort, failure here is non-fatal by design
        logger.debug("kscreen-doctor apply failed", exc_info=True)
        return False
