"""Flatpak inventory, update counts, and command builders."""

from __future__ import annotations

import logging
import os
import shlex
import shutil
from kyth_welcome.services.command import run_sync
from kyth_shared.runtime_output import parse_flatpak_apps

from .process import FLATPAK_CACHE_TTL, probe_cached, run_command

_logger = logging.getLogger(__name__)


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
    # Arch #14: after successful probe, warm AppStream JSON so Hub cold start hits cache
    try:
        from .appstream import warm_appstream_cache

        warm_appstream_cache()
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path  # nosec B110 -- best-effort, failure here is non-fatal by design
        pass
    if isinstance(raw, frozenset):
        return raw
    if isinstance(raw, (list, set, tuple)):
        return frozenset(raw)
    return None


def list_installed_apps() -> list[dict[str, str]]:
    """Return installed Flatpak applications with display metadata."""
    if not shutil.which("flatpak"):
        _logger.debug("flatpak not found on PATH — returning empty app list")
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
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
        _logger.debug("flatpak list failed: %s", exc, exc_info=True)
        return []
    if result.returncode != 0:
        _logger.debug("flatpak list returned %s: %s", result.returncode, result.stderr.strip()[:200])
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


def flatpak_override_show(app_id: str) -> str:
    """Return `flatpak override --user --show <app_id>` stdout (empty if no override)."""
    if not app_id or any(c in app_id for c in ("\0", "\n", "\r", ";", "&")):
        return ""
    try:
        r = run_sync(
            ["flatpak", "override", "--user", "--show", app_id],
            capture_output=True, text=True, timeout=8, check=False,
        )
        if r.returncode != 0:
            return ""
        return r.stdout
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        return ""
 # flatpak_override_show

def flatpak_override_command(app_id: str, filesystem: str, *, allow: bool = True) -> list[str]:
    """Build `flatpak override --user [--filesystem=|--nofilesystem=]` argv.

    Validates app_id and filesystem against allowlist so callers (Worker)
    cannot inject shell metacharacters. Returns argv for Worker/mokutil-style
    off-thread execution. Filesystem allowlist: home, xdg-documents, xdg-downloads,
    xdg-pictures, xdg-videos, host."""
    allowed_fs = {"home", "xdg-documents", "xdg-downloads", "xdg-pictures", "xdg-videos", "host"}
    if filesystem not in allowed_fs:
        raise ValueError(f"Unsupported filesystem: {filesystem}")
    if not app_id or any(c in app_id for c in ("\0", "\n", "\r", ";", "&")):
        raise ValueError(f"Invalid app_id: {app_id!r}")
    flag = f"--filesystem={filesystem}" if allow else f"--nofilesystem={filesystem}"
    return ["flatpak", "override", "--user", flag, app_id]
 # flatpak_override_command

# Compatibility names while callers migrate from services.software.
_installed_flatpak_ids = installed_app_ids
list_installed_flatpak_apps = list_installed_apps
_pending_flatpak_update_count = pending_update_count
_is_flatpak_installed = is_installed
flatpak_install_shell_command = install_shell_command


def validate_flatpak_remotes(data) -> None:
    """Strict schema for flatpak_remotes.json."""
    if not isinstance(data, list):
        raise ValueError("flatpak remotes must be a list")
    allowed = {"name","title","url","subset"}
    for e in data:
        if not isinstance(e, dict): raise ValueError(f"remote must be object: {e!r}")
        unk=set(e)-allowed
        if unk: raise ValueError(f"remote {e.get('name')} unknown keys: {unk}")
        for k in ("name","url"):
            if not isinstance(e.get(k), str) or not e.get(k): raise ValueError(f"remote missing {k}: {e!r}")
        url=e["url"]
        if not url.startswith("https://") or not url.endswith(".flatpakrepo"): raise ValueError(f"invalid url {url!r}")
        s=e.get("subset")
        if s is not None and not isinstance(s, str): raise ValueError("subset must be str or null")
