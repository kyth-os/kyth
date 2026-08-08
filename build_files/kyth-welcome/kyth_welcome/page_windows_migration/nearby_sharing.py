"""Windows Migration page — Nearby Sharing (LocalSend/KDE Connect) card + handlers, _NearbySharingMixin."""

from __future__ import annotations

import os
from ..actions import _install_flatpak_inline
from ..services.flatpak import _is_flatpak_installed
from ..services.launch import flatpak_run, popen
from ..qt import (
    QFileDialog, QHBoxLayout, QLabel, QPushButton,
)
from ..widgets import (
    _make_card,
)


class _NearbySharingMixin:
    def _build_nearby_card(self):
        # Nearby Sharing equivalents
        nearby_card, nearby_layout = _make_card("card-accent-ok")
        nearby_title = QLabel("Nearby Sharing → LocalSend and KDE Connect")
        nearby_title.setObjectName("card-title")
        nearby_layout.addWidget(nearby_title)
        nearby_body = QLabel(
            "Send files directly over your local network without uploading them first. "
            "LocalSend works across Windows, macOS, Linux, Android, and iPhone; KDE Connect "
            "adds phone notifications, clipboard sharing, and a Dolphin right-click action "
            "named Send to Nearby Device."
        )
        nearby_body.setObjectName("card-copy")
        nearby_body.setWordWrap(True)
        nearby_layout.addWidget(nearby_body)
        nearby_btns = QHBoxLayout()
        nearby_btns.setSpacing(8)
        self._localsend_btn = QPushButton()
        self._localsend_btn.setObjectName("primary")
        self._localsend_btn.clicked.connect(self._open_or_install_localsend)
        nearby_btns.addWidget(self._localsend_btn)
        send_btn = QPushButton("Send a File")
        send_btn.setToolTip("Choose files, then select a paired KDE Connect device.")
        send_btn.clicked.connect(self._send_nearby_files)
        nearby_btns.addWidget(send_btn)
        pair_btn = QPushButton("Pair a Phone or PC")
        pair_btn.clicked.connect(self._open_kde_connect)
        nearby_btns.addWidget(pair_btn)
        nearby_btns.addStretch()
        nearby_layout.addLayout(nearby_btns)
        self._nearby_status = QLabel("")
        self._nearby_status.setObjectName("card-copy")
        self._nearby_status.setWordWrap(True)
        nearby_layout.addWidget(self._nearby_status)
        self._refresh_localsend_btn()
        self._add(nearby_card)

    def _refresh_localsend_btn(self):
        installed = _is_flatpak_installed("org.localsend.localsend_app")
        self._localsend_btn.setText("Open LocalSend" if installed else "Install LocalSend")

    def _open_or_install_localsend(self):
        app_id = "org.localsend.localsend_app"
        if _is_flatpak_installed(app_id):
            try:
                flatpak_run(app_id)
                self._nearby_status.setText("LocalSend opened. Devices on the same network appear automatically.")
            except OSError as exc:
                self._nearby_status.setText(f"Could not open LocalSend: {exc}")
            return

        def _installed(code: int):
            if code == 0:
                self._localsend_btn.setEnabled(True)
                self._refresh_localsend_btn()
                self._nearby_status.setText("LocalSend installed — open it on both devices to start sharing.")

        _install_flatpak_inline(
            self, self._localsend_btn, app_id, "LocalSend", done_cb=_installed,
        )

    def _send_nearby_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Send files to a nearby device", os.path.expanduser("~")
        )
        if not paths:
            return
        helper = "/usr/bin/kyth-nearby-share"
        if not os.path.exists(helper):
            self._nearby_status.setText(
                "Nearby Sharing is available after applying the latest KythOS update and restarting."
            )
            return
        try:
            popen([helper, *paths])
            self._nearby_status.setText("Choose the destination device in the Nearby Sharing prompt.")
        except OSError as exc:
            self._nearby_status.setText(f"Could not start Nearby Sharing: {exc}")
