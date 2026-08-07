"""Post-install user, hostname, and failure handling — Phase 2 shim."""
from __future__ import annotations

from ..install import (
    _configure_hostname_timezone,
    _configure_installed_system,
    _create_installer_user,
    _handle_install_failure,
)

__all__ = [
    "_configure_hostname_timezone",
    "_configure_installed_system",
    "_create_installer_user",
    "_handle_install_failure",
]
