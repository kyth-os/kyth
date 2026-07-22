"""Compatibility facade for miscellaneous software helpers.

New code should import Flatpak, AppStream, browser, and runtime helpers from
their owning modules. The re-exports below keep older page modules working
while those imports are migrated independently.
"""

from __future__ import annotations

import glob
import os
import shlex

from .appstream import (
    _as_localized as _as_localized,
    _as_localized_desc as _as_localized_desc,
)
from .browser_apps import (
    _chromium_app_window_cmd as _chromium_app_window_cmd,
    _chromium_app_window_id as _chromium_app_window_id,
)
from .flatpak import (
    _installed_flatpak_ids as _installed_flatpak_ids,
    _is_flatpak_installed,
    _pending_flatpak_update_count as _pending_flatpak_update_count,
)
from .process import _command_stdout, _is_live_session, _run_command

_DEFAULT_FIRST_RUN_APPS = (
    ("com.valvesoftware.Steam", "Steam"),
    ("net.lutris.Lutris", "Lutris"),
    ("com.heroicgameslauncher.hgl", "Heroic"),
    ("com.usebottles.bottles", "Bottles"),
    ("com.github.mtkennerly.ludusavi", "Ludusavi"),
    ("com.dec05eba.gpu_screen_recorder", "GPU Screen Recorder"),
    ("io.github.benjamimgois.goverlay", "GOverlay"),
    ("com.brave.Browser", "Brave"),
)


def is_distrobox_container(name: str) -> bool:
    result = _run_command(["distrobox", "list", "--no-color"], timeout=10)
    return result is not None and result.returncode == 0 and name in result.stdout


_is_distrobox_container = is_distrobox_container


def refresh_desktop_database(desktop_dir: str) -> None:
    for cmd in (
        ["update-desktop-database", desktop_dir],
        ["kbuildsycoca6", "--noincremental"],
    ):
        _run_command(cmd, timeout=5)


_refresh_desktop_database = refresh_desktop_database


def _install_flatpak_inline(
    owner: object, btn, app_id: str, name: str, extra_cmd: str = "", done_cb=None
) -> None:
    """Compatibility wrapper; the widget-aware action lives outside services."""
    from ..actions import _install_flatpak_inline as install

    return install(owner, btn, app_id, name, extra_cmd=extra_cmd, done_cb=done_cb)


def _first_run_app_setup_state() -> tuple[str, str, list[str]]:
    if _is_live_session():
        return (
            "live",
            "Live sessions include the KythOS tools and launcher defaults. Install to this PC for persistent app setup.",
            [],
        )
    missing = [
        name for app_id, name in _DEFAULT_FIRST_RUN_APPS if not _is_flatpak_installed(app_id)
    ]
    done = os.path.exists("/var/lib/kyth/default-flatpaks-v10-done")
    if not missing:
        return (
            "ready",
            "Steam, game launchers, Bottles, save backup, and gaming tools are ready.",
            [],
        )
    status_path = os.path.expanduser("~/.local/share/kyth/first-run-apps.status")
    status: dict[str, str] = {}
    if os.path.exists(status_path):
        try:
            with open(status_path, encoding="utf-8") as handle:
                for line in handle:
                    if "=" in line:
                        key, value = line.rstrip("\n").split("=", 1)
                        status[key] = shlex.split(value)[0] if value else ""
        except Exception:
            status = {}
    service = _run_command(
        ["systemctl", "is-active", "kyth-default-flatpaks.service"], timeout=3
    )
    service_state = service.stdout.strip() if service and service.stdout.strip() else ""
    if service_state in {"active", "activating"} or status.get("state") == "setting_up":
        return "setting_up", f"KythOS is finishing app setup in the background. Pending: {', '.join(missing)}.", missing
    if service_state == "failed" or status.get("state") == "failed":
        return "failed", f"Default app setup needs a retry. Pending: {', '.join(missing)}.", missing
    if done:
        return "partial", f"Setup finished, but these apps are still missing: {', '.join(missing)}.", missing
    return "pending", f"Connect to the network and let KythOS finish first-run app setup. Pending: {', '.join(missing)}.", missing


def _davinci_flatpak_app_id() -> str | None:
    for app_id in (
        "com.blackmagic.Resolve",
        "com.blackmagic.ResolveStudio",
        "com.blackmagicdesign.resolve",
    ):
        if _is_flatpak_installed(app_id):
            return app_id
    return None


def _davinci_download_dir() -> str:
    candidate = _command_stdout(["xdg-user-dir", "DOWNLOAD"])
    if candidate:
        candidate = os.path.expanduser(candidate)
        if os.path.isdir(candidate):
            return candidate
    return os.path.expanduser("~/Downloads")


def _davinci_zip_candidates() -> list[str]:
    roots: list[str] = []
    for candidate in (_davinci_download_dir(), os.path.expanduser("~/Downloads")):
        expanded = os.path.abspath(os.path.expanduser(candidate))
        if os.path.isdir(expanded) and expanded not in roots:
            roots.append(expanded)
    matches: dict[str, float] = {}
    for root in roots:
        for pattern in (
            "DaVinci_Resolve*_Linux.zip",
            "DaVinci_Resolve_Studio*_Linux.zip",
            "*DaVinci*Resolve*Linux*.zip",
        ):
            for base in (root, os.path.join(root, "*")):
                for path in glob.glob(os.path.join(base, pattern)):
                    if os.path.isfile(path):
                        try:
                            matches[path] = os.path.getmtime(path)
                        except OSError:
                            matches[path] = 0
    return sorted(matches, key=lambda item: (matches[item], item.lower()), reverse=True)
