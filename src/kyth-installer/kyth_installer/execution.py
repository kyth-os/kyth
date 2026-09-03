"""Installation worker ownership and lifecycle transitions."""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from .context import InstallLifecycle, InstallationState, InstallRequest, InstallPhase


class InstallCancelled(RuntimeError):
    """Raised when user cancels before commit point."""


class InstallerExecutionError(RuntimeError):
    """Wrapper for install worker failures."""

if TYPE_CHECKING:
    from .context import InstallerContext


def start_installation(
    context: InstallerContext,
    state: InstallationState | InstallRequest,
    worker: Callable[[InstallerContext], None],
) -> bool:
    """Acquire the install slot, store validated state, and start its worker."""
    if not context.install_lock.acquire(blocking=False):
        return False
    request = state if isinstance(state, InstallRequest) else InstallRequest.from_state(state)
    context.replace_request(request)
    context.transition(InstallLifecycle.VALIDATED)

    def run() -> None:
        try:
            context.transition(InstallLifecycle.INSTALLING)
            worker(context)
        except InstallCancelled as exc:
            # Cancel before destructive commit — record as failed but with
            # user-visible cancel message, not a crash traceback.
            from .recovery import write_failure_summary
            from .config import FAILURE_SUMMARY_FILE
            try:
                context.transition(InstallLifecycle.FAILED)
            except RuntimeError:
                pass
            context.events.publish({"type": "error", "message": str(exc)})
            try:
                write_failure_summary(FAILURE_SUMMARY_FILE, context=context, message=str(exc))
            except (OSError, ValueError, RuntimeError):  # noqa: BLE001 -- narrow: failure summary persistence is best-effort
                pass
        finally:
            context.install_lock.release()
            context.cancel_requested.clear()

    threading.Thread(target=run, daemon=True).start()
    return True


def request_cancel(context: InstallerContext) -> bool:
    """Request cancellation of a running install. Returns True if running."""
    slot_held = context.install_lock.locked()
    from .orchestration import decision

    native = decision(
        "cancel-request",
        lifecycle=context.lifecycle.value,
        phase=context.phase.value,
        slot_held=slot_held,
    )
    if native is None:
        if not slot_held:
            return False
        if context.lifecycle not in (InstallLifecycle.VALIDATED, InstallLifecycle.INSTALLING):
            return False
    elif native.get("accepted") is not True:
        return False
    context.cancel_requested.set()
    context.events.publish({"type": "log", "text": "Cancellation requested — will stop at next safe point..."})
    return True


def check_cancelled(context: InstallerContext) -> None:
    """Raise InstallCancelled if user requested cancel."""
    requested = context.cancel_requested.is_set()
    phase = getattr(context, "phase", InstallPhase.PREPARE)
    from .orchestration import decision

    native = decision(
        "cancel-check",
        lifecycle=context.lifecycle.value,
        phase=phase.value,
        cancel_requested=requested,
    )
    if native is not None:
        if native.get("cancelled") is not True:
            return
        message = native.get("cancel_message")
        if not isinstance(message, str) or not message:
            raise RuntimeError("native installer cancellation response was malformed")
        raise InstallCancelled(message)
    if not requested:
        return
    destructive = (
        InstallPhase.STORAGE,
        InstallPhase.IMAGE,
        InstallPhase.CONFIGURE,
        InstallPhase.SECURE_BOOT,
    )
    if phase in destructive:
        raise InstallCancelled(
            "Installation cancelled by user. Disk changes may have already started."
        )
    raise InstallCancelled("Installation cancelled by user before disk changes were committed.")
