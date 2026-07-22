"""Desktop and container integration helpers."""

from __future__ import annotations

from .process import _run_command


def is_distrobox_container(name: str) -> bool:
    result = _run_command(["distrobox", "list", "--no-color"], timeout=10)
    return result is not None and result.returncode == 0 and name in result.stdout


def refresh_desktop_database(desktop_dir: str) -> None:
    for command in (
        ["update-desktop-database", desktop_dir],
        ["kbuildsycoca6", "--noincremental"],
    ):
        _run_command(command, timeout=5)


_is_distrobox_container = is_distrobox_container
_refresh_desktop_database = refresh_desktop_database
