"""Qt UI actions that drive service commands from buttons/labels.

Keeps widget-aware install helpers out of pure ``services/`` modules.
"""
from __future__ import annotations

import re

from .qt import QPushButton
from .services.runtime import Worker, _finish_worker
from .services.software import flatpak_install_shell_command


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
        _finish_worker(owner, attr=attr)
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
