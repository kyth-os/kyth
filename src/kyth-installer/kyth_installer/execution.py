"""Installation worker ownership and lifecycle transitions."""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from .context import InstallLifecycle, InstallationState, InstallRequest


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
            except Exception:
                pass
        finally:
            context.install_lock.release()
            context.cancel_requested.clear()

    threading.Thread(target=run, daemon=True).start()
    return True


def request_cancel(context: InstallerContext) -> bool:
    """Request cancellation of a running install. Returns True if running."""
    if not context.install_lock.locked():
        return False
    if context.lifecycle not in (InstallLifecycle.VALIDATED, InstallLifecycle.INSTALLING):
        return False
    context.cancel_requested.set()
    context.events.publish({"type": "log", "text": "Cancellation requested — will stop at next safe point..."})
    return True


def check_cancelled(context: InstallerContext) -> None:
    """Raise InstallCancelled if user requested cancel."""
    if context.cancel_requested.is_set():
        raise InstallCancelled("Installation cancelled by user before disk changes were committed.")
