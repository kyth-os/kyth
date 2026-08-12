"""Display card for HardwarePage — HDR & VRR."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .page_hardware import HardwarePage


def make_display_card(page: "HardwarePage"):
    from .qt import QDesktopServices, QHBoxLayout, QLabel, QPushButton, QUrl
    from .widgets import _make_card
    from .services.launch import kcmshell
    import pathlib

    card, layout = _make_card()
    title = QLabel("Display — HDR & Variable Refresh Rate")
    title.setObjectName("card-title")
    layout.addWidget(title)

    status_lbl = QLabel("Checking display capabilities…")
    page._display_status_lbl = status_lbl
    status_lbl.setObjectName("card-copy")
    status_lbl.setWordWrap(True)
    layout.addWidget(status_lbl)

    page._display_vrr_warn_lbl = QLabel("")
    page._display_vrr_warn_lbl.setObjectName("status-warn")
    page._display_vrr_warn_lbl.setWordWrap(True)
    page._display_vrr_warn_lbl.hide()
    layout.addWidget(page._display_vrr_warn_lbl)

    body = QLabel(
        "HDR and Variable Refresh Rate (FreeSync/G-Sync) are configured per monitor in "
        "KDE Display Settings. Enable HDR for your primary display, then set per-game "
        "HDR via Steam → game properties → General → HDR."
    )
    body.setObjectName("card-copy")
    body.setWordWrap(True)
    layout.addWidget(body)

    btns = QHBoxLayout()
    btns.setSpacing(8)
    display_btn = QPushButton("Display Settings")
    display_btn.setObjectName("primary")
    display_btn.setToolTip("Open KDE Display Settings — HDR, VRR, refresh rate, and multi-monitor layout.")
    display_btn.clicked.connect(
        lambda _=False: kcmshell("kcm_kscreen") or QDesktopServices.openUrl(QUrl("settings://display"))
    )
    btns.addWidget(display_btn)
    hdr_btn = QPushButton("HDR per-game")
    hdr_btn.setToolTip("Set per-game HDR via kyth-hdr-per-game")
    hdr_btn.clicked.connect(
        lambda _=False: __import__("kyth_welcome.services.launch", fromlist=["popen"]).popen(
            ["/usr/bin/kyth-hdr-per-game"]
        )
        if pathlib.Path("/usr/bin/kyth-hdr-per-game").exists()
        else None
    )
    btns.addWidget(hdr_btn)
    color_btn = QPushButton("Color & Night Light")
    color_btn.setToolTip("Color profiles and Night Light blue-light filter settings.")
    color_btn.clicked.connect(lambda _=False: kcmshell("kcm_nightcolor"))
    btns.addWidget(color_btn)
    btns.addStretch()
    layout.addLayout(btns)
    return card
