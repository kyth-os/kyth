"""Bluetooth audio card for HardwarePage."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .page_hardware import HardwarePage


def make_bt_audio_card(page: "HardwarePage"):
    from .qt import QDesktopServices, QHBoxLayout, QLabel, QPushButton, QUrl
    from .widgets import _make_card
    from .services.launch import kcmshell

    card, layout = _make_card()
    title = QLabel("Bluetooth Audio")
    title.setObjectName("card-title")
    layout.addWidget(title)

    desc = QLabel(
        "KythOS prefers LDAC (990 kbps HQ) over SBC when your headset supports it. "
        "If your Bluetooth headset sounds worse than expected, use the controls below "
        "to check the active codec, switch audio to your headset, or reconnect to renegotiate the codec."
    )
    desc.setObjectName("card-copy")
    desc.setWordWrap(True)
    layout.addWidget(desc)

    page._bt_status_lbl = QLabel("Click Refresh Devices to scan.")
    page._bt_status_lbl.setObjectName("card-copy")
    page._bt_status_lbl.setWordWrap(True)
    layout.addWidget(page._bt_status_lbl)

    btns = QHBoxLayout()
    btns.setSpacing(8)
    refresh_btn = QPushButton("Refresh Devices")
    refresh_btn.clicked.connect(page._refresh_bt_audio)
    btns.addWidget(refresh_btn)
    switch_btn = QPushButton("Switch to BT Output")
    switch_btn.setToolTip("Set the connected Bluetooth audio device as the default audio output.")
    switch_btn.clicked.connect(page._switch_to_bt_audio)
    btns.addWidget(switch_btn)
    ldac_btn = QPushButton("Force LDAC Reconnect")
    ldac_btn.setToolTip(
        "Disconnect and reconnect the active Bluetooth device to renegotiate codec. "
        "Use this if your headset falls back to SBC instead of LDAC."
    )
    ldac_btn.clicked.connect(page._force_ldac_reconnect)
    btns.addWidget(ldac_btn)
    easy_btn = QPushButton("Mic Effects (EasyEffects)")
    easy_btn.setToolTip("Open EasyEffects for noise gate/EQ — for headset mic parity")
    easy_btn.clicked.connect(
        lambda: __import__("shutil").which("easyeffects")
        and __import__("kyth_welcome.services.launch", fromlist=["popen"]).popen(
            ["flatpak", "run", "com.github.wwmm.easyeffects"]
        )
        or __import__("kyth_welcome.services.launch", fromlist=["popen"]).popen(
            ["flatpak", "run", "com.github.wwmm.easyeffects"]
        )
    )
    btns.addWidget(easy_btn)
    bt_settings_btn = QPushButton("Bluetooth Settings")
    bt_settings_btn.clicked.connect(
        lambda: kcmshell("kcm_bluetooth") or QDesktopServices.openUrl(QUrl("settings://bluetooth"))
    )
    btns.addWidget(bt_settings_btn)
    btns.addStretch()
    layout.addLayout(btns)
    return card
