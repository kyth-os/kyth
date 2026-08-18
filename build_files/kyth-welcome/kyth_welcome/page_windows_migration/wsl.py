"""Windows Migration page — "Where's my WSL?" (Distrobox) card + handlers, _WslMixin."""

from __future__ import annotations

import shutil
from ..services.runtime import Worker, guard_disposed, release_worker_when_finished
from ..services.launch import popen
from ..qt import (
    QHBoxLayout, QLabel, QPushButton,
)
from ..widgets import (
    _make_card,
)


class _WslMixin:
    def _build_wsl_card(self):
        # ── WSL equivalent ────────────────────────────────────────────────────
        wsl_card, wsl_layout = _make_card()
        wsl_title = QLabel("Where's my WSL?")
        wsl_title.setObjectName("card-title")
        wsl_layout.addWidget(wsl_title)
        wsl_body = QLabel(
            "For Linux subsystem workflows gave you a Linux environment inside your OS. Here the whole OS "
            "is Linux — but the same workflow exists as Distrobox: full distros in containers "
            "that share your home folder, with no VM overhead. One click creates an Ubuntu "
            "environment; opening a terminal in it works just like typing wsl in PowerShell."
        )
        wsl_body.setObjectName("card-copy")
        wsl_body.setWordWrap(True)
        wsl_layout.addWidget(wsl_body)
        self._wsl_status = QLabel("")
        self._wsl_status.setObjectName("card-copy")
        self._wsl_status.setWordWrap(True)
        wsl_layout.addWidget(self._wsl_status)
        wsl_btns = QHBoxLayout()
        wsl_btns.setSpacing(8)
        self._wsl_create_btn = QPushButton("Create Ubuntu Box")
        self._wsl_create_btn.setObjectName("primary")
        self._wsl_create_btn.clicked.connect(self._create_wsl_box)
        wsl_btns.addWidget(self._wsl_create_btn)
        self._wsl_open_btn = QPushButton("Open Ubuntu Terminal")
        self._wsl_open_btn.clicked.connect(self._open_wsl_terminal)
        wsl_btns.addWidget(self._wsl_open_btn)
        wsl_btns.addStretch()
        wsl_layout.addLayout(wsl_btns)
        self._add(wsl_card)

    def _create_wsl_box(self):
        if self._wsl_worker is not None and self._wsl_worker.isRunning():
            return
        self._wsl_create_btn.setEnabled(False)
        self._wsl_status.setText(
            "Creating the Ubuntu box — the first run downloads the image (a few hundred MB)…"
        )
        script = (
            "set -e\n"
            "command -v distrobox >/dev/null 2>&1 || { echo 'distrobox is not installed.'; exit 1; }\n"
            "if distrobox list --no-color 2>/dev/null | awk -F'|' '{print $2}' | grep -qw ubuntu; then\n"
            "    echo 'already exists'\n"
            "    exit 0\n"
            "fi\n"
            "distrobox create --image ubuntu:24.04 --name ubuntu --yes\n"
        )
        worker = Worker(["bash", "-c", script])

        def _done(code: int):
            self._wsl_create_btn.setEnabled(True)
            if code == 0:
                self._wsl_status.setText(
                    "✓ Ubuntu box ready. Open Ubuntu Terminal drops you at a bash prompt "
                    "with apt available — your home folder is shared with KythOS."
                )
            else:
                self._wsl_status.setText(
                    "Could not create the Ubuntu box. Check the network connection and try again."
                )
        worker.done.connect(guard_disposed(_done))
        self._wsl_worker = worker
        release_worker_when_finished(self, "_wsl_worker", worker)
        worker.start()

    def _open_wsl_terminal(self):
        if not shutil.which("konsole"):
            self._wsl_status.setText("Konsole is not available in this session.")
            return
        popen(["konsole", "-e", "distrobox", "enter", "ubuntu"])
        self._wsl_status.setText(
            "If the box doesn't exist yet, the terminal will say so — use Create Ubuntu Box first."
        )