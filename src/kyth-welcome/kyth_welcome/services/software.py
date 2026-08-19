"""Compatibility facade for software helpers.

New code should import Flatpak, AppStream, browser, and runtime helpers from
their owning modules. The re-exports below keep older page modules working
while those imports are migrated independently.
"""

from __future__ import annotations

from .appstream import (
    _as_localized as _as_localized,
    _as_localized_desc as _as_localized_desc,
)
from .browser_apps import (
    _chromium_app_window_cmd as _chromium_app_window_cmd,
    _chromium_app_window_id as _chromium_app_window_id,
)
from .creator import (
    davinci_download_dir as _davinci_download_dir,
    davinci_flatpak_app_id as _davinci_flatpak_app_id,
    davinci_zip_candidates as _davinci_zip_candidates,
)
from .desktop import (
    is_distrobox_container,
    refresh_desktop_database,
)
from .flatpak import (
    _installed_flatpak_ids as _installed_flatpak_ids,
    is_installed as _is_flatpak_installed,
    _pending_flatpak_update_count as _pending_flatpak_update_count,
)
from .first_run import (
    DEFAULT_FIRST_RUN_APPS as _DEFAULT_FIRST_RUN_APPS,
    app_setup_state as _first_run_app_setup_state,
)


_is_distrobox_container = is_distrobox_container
_refresh_desktop_database = refresh_desktop_database


def _install_flatpak_inline(
    owner: object, btn, app_id: str, name: str, extra_cmd: str = "", done_cb=None
) -> None:
    """Compatibility wrapper; the widget-aware action lives outside services."""
    from ..actions import _install_flatpak_inline as install

    return install(owner, btn, app_id, name, extra_cmd=extra_cmd, done_cb=done_cb)


def find_familiar_app_match(
    query: str, apps: list[tuple[str, str, str]]
) -> tuple[str, str, str] | None:
    """First (name, desc, app_id) in `apps` whose name contains, or is
    contained by, `query` (case-insensitive). `apps` is checked in its
    curated order, so an earlier/more specific entry wins over a later,
    broader one."""
    lower = query.strip().lower()
    if not lower:
        return None
    for name, desc, app_id in apps:
        if lower in name.lower() or name.lower() in lower:
            return (name, desc, app_id)
    return None
