"""Wizard step builders — _FinishStepMixin."""
from __future__ import annotations

import subprocess
from typing import ClassVar

from ..qt import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class _FinishStepMixin:
    def _make_finish_step(self) -> QWidget:
        page = QWidget()
        page.setObjectName("content-area")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(72, 0, 72, 0)
        layout.setSpacing(0)
        layout.addStretch()

        check = QLabel("✓")
        check.setStyleSheet(
            "font-size: 52px; color: #6ccb5f; font-weight: 300; background: transparent;"
        )
        layout.addWidget(check)
        layout.addSpacing(18)

        title = QLabel("You're all set.")
        title.setObjectName("finish-title")
        layout.addWidget(title)
        layout.addSpacing(10)

        subtitle = QLabel(
            "Open Steam, go to Settings → Compatibility, and enable Proton for all titles.\n"
            "Your full game library will appear and be ready to install.\n\n"
            "If an update makes games worse, open System Hub → Update and use Roll Back "
            "before reinstalling anything. The System Hub is always available from the app menu."
        )
        subtitle.setObjectName("finish-subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(36)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        steam_btn = QPushButton("Open Steam")
        steam_btn.setObjectName("primary")
        steam_btn.clicked.connect(lambda: subprocess.Popen(["flatpak", "run", "com.valvesoftware.Steam"]))
        btn_row.addWidget(steam_btn)
        self._finish_work_btn = QPushButton("Open Work Setup")
        self._finish_work_btn.setToolTip(
            "Office apps, Microsoft 365 shortcuts, document fonts, VPN, shares, and printing."
        )
        self._finish_work_btn.clicked.connect(lambda: self._open_hub_at("Work Setup"))
        self._finish_work_btn.setVisible(self._profile == "everyday")
        btn_row.addWidget(self._finish_work_btn)
        hub_btn = QPushButton("Open System Hub")
        hub_btn.clicked.connect(lambda: (self._next_btn.click() or None))
        btn_row.addWidget(hub_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch()
        return page

    # ── Usage profile ──────────────────────────────────────────────────────────

    _PROFILE_DEFAULT_APPS: ClassVar[dict[str, set[str]]] = {
        "gaming": {"com.valvesoftware.Steam", "com.discordapp.Discord"},
        "everyday": {"org.libreoffice.LibreOffice", "eu.betterbird.Betterbird"},
    }


