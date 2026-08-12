"""Shared UI/session helpers for System Hub pages.

Domain logic lives under ``services/`` (process, bootc, registry, runtime) —
pages import those directly. This module only holds the Qt/session-facing
helpers that don't have a more specific home: window-close/worker-cancel
plumbing, the usage-profile file, and small widget utilities.
"""
from __future__ import annotations

import os
import re
import time

from kyth_welcome.services.command import run_sync
from kyth_welcome.services.process import is_live_session, run_command
from kyth_welcome.services.runtime import TASK_SUPERVISOR, Worker

from .qt import (
    QLabel, QPushButton, QTextEdit, QWidget,
)

# ── Constants still used by pages ─────────────────────────────────────────────
CLOUD_SYNC_CONFIG = os.path.expanduser("~/.config/kyth-cloud-sync.json")
SYNC_INTERVAL_MS = 5 * 60 * 1000  # 5 minutes
SMB_CONFIG = os.path.expanduser("~/.config/kyth-smb-shares.json")
SMB_CREDS_DIR = "/etc/kyth-smb-creds"


IS_LIVE = is_live_session()


def prefer_xwayland_if_wayland_plugin_missing() -> None:
    # KDE Wayland sessions usually expose both WAYLAND_DISPLAY and DISPLAY.
    # If qt6-qtwayland is missing in the image, Qt aborts before showing any
    # window; falling back to xcb lets the helper still open via XWayland.
    if os.environ.get("QT_QPA_PLATFORM"):
        return
    if not os.environ.get("WAYLAND_DISPLAY") or not os.environ.get("DISPLAY"):
        return

    # Use filesystem scan so this runs safely before QApplication is created
    # (QLibraryInfo.path() can initialize Qt internals that produce ghost windows).
    QT6_PLATFORM_DIRS = [
        "/usr/lib64/qt6/plugins/platforms",
        "/usr/lib/qt6/plugins/platforms",
        "/usr/lib/x86_64-linux-gnu/qt6/plugins/platforms",
        "/usr/lib/aarch64-linux-gnu/qt6/plugins/platforms",
    ]
    # Also check pip wheel locations (PySide6/PyQt6 bundle Qt under site-packages).
    try:
        import importlib.util as _ilu

        for _binding in ("PySide6", "PyQt6"):
            _spec = _ilu.find_spec(_binding)
            if _spec and _spec.origin:
                _wheel_dir = os.path.join(
                    os.path.dirname(_spec.origin), "Qt", "plugins", "platforms"
                )
                if _wheel_dir not in QT6_PLATFORM_DIRS:
                    QT6_PLATFORM_DIRS.append(_wheel_dir)
    except Exception:
        pass
    for platform_dir in QT6_PLATFORM_DIRS:
        if not os.path.isdir(platform_dir):
            continue
        try:
            names = os.listdir(platform_dir)
        except OSError:
            continue
        if any(
            n == "libqwayland.so"
            or n.startswith("libqwayland-")
            or n == "libqwayland-generic.so"
            or n == "libqwayland-egl.so"
            for n in names
        ):
            return  # wayland platform plugin present — use it
        # Only force xcb if its plugin actually exists in this dir;
        # otherwise leave Qt's default chooser alone.
        if "libqxcb.so" in names:
            os.environ["QT_QPA_PLATFORM"] = "xcb"
        return
    # No platform dir found at all — don't force; let Qt choose (wayland via wheel may still work).


def apply_install_badge(lbl: QLabel, ok: bool, ok_text: str = "Installed",
                         warn_text: str = "Not Installed") -> None:
    lbl.setText(ok_text if ok else warn_text)
    lbl.setObjectName("status-ok" if ok else "status-dim")
    restyle(lbl)


def cancel_worker(
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
        restyle(status_lbl)
    if log is not None:
        log.append("\nCancel requested. Waiting for the running command to stop...")
        log.ensureCursorVisible()
    worker.cancel()
    return True


def set_session_inhibit(owner: object, reason: str | None = None) -> None:
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
            run_sync(cmd, capture_output=True, text=True, timeout=5, check=False)
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
        result = run_sync(cmd, capture_output=True, text=True, timeout=5, check=False)
    except OSError:
        return

    if result.returncode != 0:
        return

    match = re.search(r"\((\d+),\)", result.stdout)
    if match:
        owner._screen_inhibit_cookie = int(match.group(1))


def run_worker(
    owner: object,
    cmd: list[str],
    *,
    on_line,
    on_done,
    attr: str = "_worker",
    input_text: str | None = None,
    session_inhibit_reason: str | None = None,
) -> Worker:
    """Construct, wire, and start a Worker stored on owner.<attr>.

    Collapses the ubiquitous ``self._worker = Worker(cmd);
    self._worker.finished.connect(lambda: setattr(self, "_worker", None))
    self._worker.finished.connect(self._worker.deleteLater)
    self._worker.line.connect(on_line); self._worker.done.connect(on_done);
    self._worker.start()`` sequence — optionally preceded by a session-inhibit
    call, in the same order pages already issue it — repeated across pages.
    """
    worker = Worker(cmd, input_text=input_text)
    setattr(owner, attr, worker)
    TASK_SUPERVISOR.attach(worker, owner, attr, task_id=attr.removeprefix("_"))
    if session_inhibit_reason is not None:
        set_session_inhibit(owner, session_inhibit_reason)
    worker.line.connect(on_line)
    worker.done.connect(on_done)
    worker.start()
    return worker


def remove_autostart():
    path = os.path.expanduser("~/.config/autostart/kyth-welcome.desktop")
    try:
        os.remove(path)
    except OSError:
        pass


def is_first_run() -> bool:
    from .services.setup_state import is_first_run as _is_first_run_impl
    return _is_first_run_impl()


# ── Usage profile (everyday / gaming) ─────────────────────────────────────────
# Chosen on the first-run wizard's welcome step; drives which app defaults the
# wizard pre-selects and which System Hub sections get the most prominence.
# Older installs used work/both; both are treated as the Everyday preset.
# Roadmap 3-6M: creator/developer/laptop/docked presets — added as aliases
# that resolve to the nearest existing preset until dedicated Hub sections exist.
PROFILE_PATH = os.path.expanduser("~/.local/share/kyth/profile")
VALID_PROFILES = ("everyday", "gaming", "creator", "developer", "laptop", "docked")
PROFILE_ALIASES = {
    "work": "everyday",
    "both": "everyday",
    "creator": "creator",
    "developer": "developer",
    "laptop": "laptop",
    "docked": "docked",
}


def normalize_profile(profile: str) -> str:
    value = profile.strip().lower()
    value = PROFILE_ALIASES.get(value, value)
    return value if value in VALID_PROFILES else "everyday"


def load_profile() -> str:
    try:
        with open(PROFILE_PATH, encoding="utf-8") as fh:
            return normalize_profile(fh.read())
    except OSError:
        return "everyday"


def save_profile(profile: str) -> None:
    profile = normalize_profile(profile)
    try:
        os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
        with open(PROFILE_PATH, "w", encoding="utf-8") as fh:
            fh.write(profile + "\n")
    except OSError:
        pass


def wait_for_display_setup(timeout: float = 8.0, interval: float = 0.25):
    """C3: must not be called on the GUI thread — blocks for up to 8 s.

    Callers in the wizard/live path run this before QApplication is created
    (safe). Pages must not call it from showEvent/__init__; use a DataWorker
    or QTimer instead.
    """
    autostart = os.path.expanduser("~/.config/autostart/kyth-set-resolution.desktop")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = run_command(["pgrep", "-af", "kyth-set-resolution"], timeout=2)
        running = bool(result is not None and result.returncode == 0 and result.stdout.strip())
        pending = os.path.exists(autostart)
        if not running and not pending:
            return
        time.sleep(interval)


# ── UI utilities ───────────────────────────────────────────────────────────────

def restyle(widget: QWidget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
