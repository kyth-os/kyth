"""System Hub shared entry surface.

Domain logic lives under ``services/``:
  process  — subprocess helpers + probe cache
  bootc    — bootc status / branch / deployment
  registry — skopeo/registry digest checks
  runtime  — Qt worker threads

This module re-exports those APIs under the historical underscore names and
keeps UI/session helpers that pages still import from here.
"""
# pylint: disable=unused-import
# Most imports below are deliberate re-exports under the historical
# underscore names described above, not used directly in this file.

from __future__ import annotations

import os
import re
import subprocess
import time

# __KYTH_GENERATED_IMPORTS__
from .qt import (  # noqa: E501
    QLabel, QPushButton, QTextEdit, QWidget,
)

# ── Re-exports: process ───────────────────────────────────────────────────────
from .services.process import (  # noqa: F401
    _BOOTC_CACHE_TTL,
    _FLATPAK_CACHE_TTL,
    _command_stdout,
    _get_disk_write_bytes,
    _get_rx_bytes,
    _human_bytes,
    _human_bytes_pair,
    _invalidate_probe_caches,
    _is_live_session,
    _parse_size_bytes,
    _probe_cached,
    _run_command,
    _with_idle_inhibit,
)

# ── Re-exports: bootc ─────────────────────────────────────────────────────────
from .services.bootc import (  # noqa: F401
    REGISTRY,
    _active_bootc_operation,
    _bootc_cancel_block_reason,
    _bootc_image_digest,
    _bootc_image_reference,
    _bootc_image_timestamp,
    _bootc_proxy_running,
    _bootc_status_data,
    _bootc_status_text,
    _branch_display_name,
    _branch_from_ref,
    _current_branch,
    _current_kernel_flavor,
    _default_phase,
    _fetch_bootc_status_data,
    _fetch_bootc_status_text,
    _has_rollback_deployment,
    _has_staged_update,
    _image_tag_for_channel,
    _image_tag_for_kernel,
    _nested_get,
    _parse_update_phase,
    _walk_strings,
)

# ── Re-exports: runtime (Qt workers) ──────────────────────────────────────────
from .services.runtime import (  # noqa: F401
    DataWorker,
    DownloadMonitor,
    TrackedThread,
    Worker,
    _finish_worker,
    _release_worker_when_finished,
    _running_threads,
    _shutdown_threads,
)

# ── Constants still used by pages ─────────────────────────────────────────────
_CLOUD_SYNC_CONFIG = os.path.expanduser("~/.config/kyth-cloud-sync.json")
_SYNC_INTERVAL_MS = 5 * 60 * 1000  # 5 minutes
_WIZARD_SENTINEL = os.path.expanduser("~/.config/kyth-welcome-done")
_SMB_CONFIG = os.path.expanduser("~/.config/kyth-smb-shares.json")
_SMB_CREDS_DIR = "/etc/kyth-smb-creds"


_IS_LIVE = _is_live_session()


def _prefer_xwayland_if_wayland_plugin_missing() -> None:
    # KDE Wayland sessions usually expose both WAYLAND_DISPLAY and DISPLAY.
    # If qt6-qtwayland is missing in the image, Qt aborts before showing any
    # window; falling back to xcb lets the helper still open via XWayland.
    if os.environ.get("QT_QPA_PLATFORM"):
        return
    if not os.environ.get("WAYLAND_DISPLAY") or not os.environ.get("DISPLAY"):
        return

    # Use filesystem scan so this runs safely before QApplication is created
    # (QLibraryInfo.path() can initialize Qt internals that produce ghost windows).
    _QT6_PLATFORM_DIRS = [
        "/usr/lib64/qt6/plugins/platforms",
        "/usr/lib/qt6/plugins/platforms",
        "/usr/lib/x86_64-linux-gnu/qt6/plugins/platforms",
        "/usr/lib/aarch64-linux-gnu/qt6/plugins/platforms",
    ]
    for platform_dir in _QT6_PLATFORM_DIRS:
        if not os.path.isdir(platform_dir):
            continue
        if any(
            name.startswith("libqwayland-") or name == "libqwayland-generic.so"
            for name in os.listdir(platform_dir)
        ):
            return  # wayland platform plugin present — use it
        os.environ["QT_QPA_PLATFORM"] = "xcb"
        return
    os.environ["QT_QPA_PLATFORM"] = "xcb"


def _apply_install_badge(lbl: QLabel, ok: bool, ok_text: str = "Installed",
                         warn_text: str = "Not Installed") -> None:
    if ok:
        bg = "#121e2d"
        fg = "#4fc1ff"
        border = "#1c3d60"
        text = ok_text
    else:
        bg = "#171d27"
        fg = "#a9b5c7"
        border = "#2e394c"
        text = warn_text

    lbl.setText(f"  {text}  ")
    lbl.setStyleSheet(
        f"background: {bg}; color: {fg}; border: 1px solid {border}; "
        "border-radius: 10px; padding: 3px 8px; font-size: 11px; "
        "font-weight: 700; letter-spacing: 0.2px;"
    )


def _cancel_worker(
    owner: object,
    attr: str = "_worker",
    status_lbl: QLabel | None = None,
    log: QTextEdit | None = None,
    cancel_btn: QPushButton | None = None,
    message: str = "Cancelling...",
) -> bool:
    worker = getattr(owner, attr, None)
    if worker is None or not worker.isRunning() or not hasattr(worker, "cancel"):
        return False
    if cancel_btn is not None:
        cancel_btn.setEnabled(False)
    if status_lbl is not None:
        status_lbl.setText(message)
        status_lbl.setObjectName("status-warn")
        status_lbl.show()
        _restyle(status_lbl)
    if log is not None:
        log.append("\nCancel requested. Waiting for the running command to stop...")
        log.ensureCursorVisible()
    worker.cancel()
    return True


def _set_session_inhibit(owner: object, reason: str | None = None) -> None:
    current = getattr(owner, "_screen_inhibit_cookie", None)
    if reason is None:
        if current is None:
            return
        cmd = [
            "gdbus", "call", "--session",
            "--dest", "org.freedesktop.ScreenSaver",
            "--object-path", "/ScreenSaver",
            "--method", "org.freedesktop.ScreenSaver.UnInhibit",
            str(current),
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
        finally:
            owner._screen_inhibit_cookie = None
        return

    if current is not None:
        return

    cmd = [
        "gdbus", "call", "--session",
        "--dest", "org.freedesktop.ScreenSaver",
        "--object-path", "/ScreenSaver",
        "--method", "org.freedesktop.ScreenSaver.Inhibit",
        "kyth-welcome", reason,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
    except OSError:
        return

    if result.returncode != 0:
        return

    match = re.search(r"\((\d+),\)", result.stdout)
    if match:
        owner._screen_inhibit_cookie = int(match.group(1))


def _remove_autostart():
    path = os.path.expanduser("~/.config/autostart/kyth-welcome.desktop")
    try:
        os.remove(path)
    except OSError:
        pass


def _is_first_run() -> bool:
    return not os.path.exists(_WIZARD_SENTINEL)


def _mark_wizard_done():
    try:
        os.makedirs(os.path.dirname(_WIZARD_SENTINEL), exist_ok=True)
        open(_WIZARD_SENTINEL, "w").close()
    except OSError:
        pass


# ── Usage profile (everyday / gaming) ─────────────────────────────────────────
# Chosen on the first-run wizard's welcome step; drives which app defaults the
# wizard pre-selects and which System Hub sections get the most prominence.
# Older installs used work/both; both are treated as the Everyday preset.
_PROFILE_PATH = os.path.expanduser("~/.local/share/kyth/profile")
_VALID_PROFILES = ("everyday", "gaming")
_PROFILE_ALIASES = {"work": "everyday", "both": "everyday"}


def _normalize_profile(profile: str) -> str:
    value = profile.strip().lower()
    value = _PROFILE_ALIASES.get(value, value)
    return value if value in _VALID_PROFILES else "everyday"


def _load_profile() -> str:
    try:
        with open(_PROFILE_PATH, encoding="utf-8") as fh:
            return _normalize_profile(fh.read())
    except OSError:
        return "everyday"


def _save_profile(profile: str) -> None:
    profile = _normalize_profile(profile)
    try:
        os.makedirs(os.path.dirname(_PROFILE_PATH), exist_ok=True)
        with open(_PROFILE_PATH, "w", encoding="utf-8") as fh:
            fh.write(profile + "\n")
    except OSError:
        pass


def _wait_for_display_setup(timeout: float = 8.0, interval: float = 0.25):
    autostart = os.path.expanduser("~/.config/autostart/kyth-set-resolution.desktop")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _run_command(["pgrep", "-af", "kyth-set-resolution"], timeout=2)
        running = bool(result is not None and result.returncode == 0 and result.stdout.strip())
        pending = os.path.exists(autostart)
        if not running and not pending:
            return
        time.sleep(interval)


# ── UI utilities ───────────────────────────────────────────────────────────────

def _restyle(widget: QWidget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
