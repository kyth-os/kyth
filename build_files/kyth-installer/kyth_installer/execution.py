"""Installation worker ownership and lifecycle transitions."""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from .context import InstallLifecycle, InstallationState

if TYPE_CHECKING:
    from .context import InstallerContext


def start_installation(
    context: InstallerContext,
    state: InstallationState,
    worker: Callable[[InstallerContext], None],
) -> bool:
    """Acquire the install slot, store validated state, and start its worker."""
    if not context.install_lock.acquire(blocking=False):
        return False
    context.replace_state(state)
    context.transition(InstallLifecycle.VALIDATED)

    def run() -> None:
        try:
            context.transition(InstallLifecycle.INSTALLING)
            worker(context)
        finally:
            context.install_lock.release()

    threading.Thread(target=run, daemon=True).start()
    return True
