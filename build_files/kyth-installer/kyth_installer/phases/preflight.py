"""Install context and storage preflight — thin wrapper over plan/install.

Phase 2 shim: re-exports preflight helpers so callers can import from
`kyth_installer.phases.preflight` instead of the 870-LOC `install.py`/
`plan.py` god modules. Full logic remains in `install.py` until the
follow-on split moves it here verbatim; this shim already breaks the
import cycle and gives the test suite a stable `phases` entry point.
"""
from __future__ import annotations

from ..config import SKIP_FETCH_CHECK
from ..context import InstallerContext, InstallPhase
from ..imagesrc import _install_images, _network_preflight
from ..plan import _prepare_install_plan, _validate_install_target, _validate_storage_intent
from .common import _push
from .storage import _prepare_partition_target_storage, _prepare_wipe_disk_storage  # noqa: F401

__all__ = [
    "_prepare_install_context",
]


def _prepare_install_context(log, context: InstallerContext):
    """Delegates to `kyth_installer.install._prepare_install_context`."""
    from ..install import _prepare_install_context as _orig

    return _orig(log, context)
