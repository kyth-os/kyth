"""Flatpak inventory, update counts, and command builders."""

from __future__ import annotations

import os
import shlex
import shutil
from kyth_welcome.services.command import run_sync
from kyth_shared.runtime_output import parse_flatpak_apps

from .process import FLATPAK_CACHE_TTL, probe_cached, run_command


def installed_app_ids() -> frozenset[str] | None:
    """Return one cached Flatpak application-ID snapshot."""

    def fetch() -> list[str] | None:
        result = run_command(
            ["flatpak", "list", "--app", "--columns=application"], timeout=10
        )
        if result is None or result.returncode != 0:
            return None
        return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})

    raw = probe_cached("flatpak-apps", FLATPAK_CACHE_TTL, fetch)
    if raw is None:
        return None
    if isinstance(raw, frozenset):
        return raw
    if isinstance(raw, (list, set, tuple)):
        return frozenset(raw)
    return None


def list_installed_apps() -> list[dict[str, str]]:
    """Return installed Flatpak applications with display metadata."""
    if not shutil.which("flatpak"):
        return []
    env = {**os.environ, "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}
    try:
        result = run_sync(
            ["flatpak", "list", "--app", "--columns=application,name,origin,installation"],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
            env=env,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    return parse_flatpak_apps(result.stdout)


def pending_update_count() -> int | None:
    """Return cached pending system and user Flatpak application updates."""

    def fetch() -> int | None:
        from .probe import _count_flatpak_updates

        return _count_flatpak_updates()

    return probe_cached("flatpak-updates", FLATPAK_CACHE_TTL, fetch)


def is_installed(app_id: str) -> bool:
    ids = installed_app_ids()
    if ids is not None:
        return app_id in ids
    result = run_command(["flatpak", "info", app_id], timeout=8)
    return result is not None and result.returncode == 0


def install_shell_command(app_id: str, extra_cmd: str = "") -> str:
    """Build the legacy shell command used by the generic UI task runner."""
    cmd = (
        "flatpak remote-add --if-not-exists flathub "
        "https://dl.flathub.org/repo/flathub.flatpakrepo"
        f" && flatpak install -y --or-update flathub {shlex.quote(app_id)}"
    )
    if extra_cmd:
        cmd += f" && {extra_cmd}"
    return cmd


# Compatibility names while callers migrate from services.software.
_installed_flatpak_ids = installed_app_ids
list_installed_flatpak_apps = list_installed_apps
_pending_flatpak_update_count = pending_update_count
_is_flatpak_installed = is_installed
flatpak_install_shell_command = install_shell_command
