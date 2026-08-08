"""Qt UI actions that drive service commands from buttons/labels.

Keeps widget-aware install helpers out of pure ``services/`` modules.
"""
from __future__ import annotations

import re

from .qt import QMessageBox, QPushButton
from .services.browser_apps import _chromium_app_window_cmd
from .services.launch import popen
from .services.runtime import Worker, finish_worker
from .services.flatpak import flatpak_install_shell_command


def _install_flatpak_inline(owner: object, btn: QPushButton, app_id: str, name: str,
                            extra_cmd: str = "", done_cb=None) -> None:
    """Install a Flathub app on a Worker thread, driving the button state.

    In-app replacement for terminal-popping installs: the button itself shows
    progress and outcome, and polkit/askpass handles any elevation. extra_cmd
    is shell appended after a successful install (e.g. a flatpak override).
    One worker per app id, kept on `owner` so concurrent clicks are ignored.
    """
    attr = "_inline_install_" + re.sub(r"\W", "_", app_id)
    existing = getattr(owner, attr, None)
    if existing is not None and existing.isRunning():
        return
    orig = btn.text()
    btn.setEnabled(False)
    btn.setText("Installing…")
    cmd = flatpak_install_shell_command(app_id, extra_cmd=extra_cmd)
    worker = Worker(["bash", "-c", cmd])

    def _done(code: int):
        finish_worker(owner, attr=attr)
        if code == 0:
            btn.setText("✓ Installed")
            btn.setToolTip(f"{name} is installed. Find it in the app launcher.")
        else:
            btn.setText(orig)
            btn.setEnabled(True)
            btn.setToolTip(
                f"Install failed (exit {code}). Check your network connection and try again."
            )
        if done_cb:
            done_cb(code)

    worker.done.connect(_done)
    setattr(owner, attr, worker)
    worker.start()


def _open_chromium_webapp(owner: object, url: str, *, extra_hint: str = "") -> None:
    """Open `url` in a dedicated Chromium-family app window.

    Used for web-app shortcuts (e.g. Microsoft 365) that should feel like
    native apps rather than browser tabs.
    """
    launch = _chromium_app_window_cmd(url)
    if launch is None:
        message = (
            "Opening web app shortcuts needs a Chromium-family browser "
            "(Brave, Chromium, Edge, or Chrome), but none was found."
        )
        if extra_hint:
            message += f"\n\n{extra_hint}"
        QMessageBox.warning(owner, "No browser found", message)
        return
    try:
        popen(launch[0])
    except OSError as exc:
        QMessageBox.warning(owner, "Could not open web app", str(exc))
