"""Install context and storage preflight — thin wrapper over plan/install.

Phase 2 shim: re-exports preflight helpers so callers can import from
`kyth_installer.phases.preflight` instead of the 870-LOC `install.py`/
`plan.py` god modules. Full logic remains in `install.py` until the
follow-on split moves it here verbatim; this shim already breaks the
import cycle and gives the test suite a stable `phases` entry point.
"""
from __future__ import annotations

from ..context import InstallerContext

__all__ = [
    "_prepare_install_context",
]


def _prepare_install_context(log, context: InstallerContext):
    """Delegates to `kyth_installer.install._prepare_install_context`."""
    from ..install import _prepare_install_context as _orig

    return _orig(log, context)
