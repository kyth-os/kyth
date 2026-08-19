"""Explicit cleanup operations for installer mounts and sensitive state."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .context import InstallationState
from .runner import run_command
from .system import _as_root

RunCommand = Callable[..., Any]


def unmount_configuration(
    config_root: str,
    alongside_mount: str,
    *,
    run: RunCommand = run_command,
) -> None:
    """Sync writes and release mounts created for installed-system configuration."""
    run(_as_root(["sync"]), check=False)
    if alongside_mount:
        target_home = Path(alongside_mount) / "ostree/deploy/default/var/home"
        run(_as_root(["umount", "-Rl", str(target_home)]), check=False, capture_output=True)
        run(_as_root(["umount", "-Rl", alongside_mount]), check=False, capture_output=True)
    else:
        run(_as_root(["umount", config_root]), check=False)


def clear_secrets_and_orphan_mount(
    state: InstallationState,
    alongside_mount: str,
    *,
    run: RunCommand = run_command,
) -> None:
    """Clear request secrets and detach an orphaned alongside mount, if any."""
    state["password_hash"] = ""  # nosec B105 # nosemgrep -- clearing, not a hardcoded secret
    state["mok_password"] = ""  # nosec B105 # nosemgrep -- clearing, not a hardcoded secret
    if alongside_mount:
        run(_as_root(["umount", "-Rl", alongside_mount]), check=False, capture_output=True)
