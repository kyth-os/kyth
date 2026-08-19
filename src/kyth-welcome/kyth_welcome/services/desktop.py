"""Desktop and container integration helpers."""

from __future__ import annotations

from .process import run_command


def is_distrobox_container(name: str) -> bool:
    result = run_command(["distrobox", "list", "--no-color"], timeout=10)
    return result is not None and result.returncode == 0 and name in result.stdout


def refresh_desktop_database(desktop_dir: str) -> None:
    for command in (
        ["update-desktop-database", desktop_dir],
        ["kbuildsycoca6", "--noincremental"],
    ):
        run_command(command, timeout=5)


# Shell equivalent of refresh_desktop_database() for callers that build a
# ["bash", "-c", ...] command list run by a streaming/QThread runner rather
# than calling run_command() directly (e.g. a quick-fix button whose output
# is shown live in a log widget). Always targets the invoking user's own
# applications dir, so it takes no argument.
REFRESH_DESKTOP_DATABASE_SH = (
    'update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true; '
    "kbuildsycoca6 --noincremental 2>/dev/null || true"
)

_is_distrobox_container = is_distrobox_container
_refresh_desktop_database = refresh_desktop_database
