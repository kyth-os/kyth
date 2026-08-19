"""Family / Nearby / Phone hub — unified Devices card, _FamilyHubMixin."""
from __future__ import annotations

from ..qt import QHBoxLayout, QLabel, QPushButton
from ..widgets import _make_card


class _FamilyHubMixin:
    def _build_family_hub_card(self):
        card, layout = _make_card("card-accent-ok")
        title = QLabel("Family, Nearby & Phone — your devices in one place")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Windows shows Nearby Share + Phone Link in one spot. This hub unifies LocalSend (Quick Share / Nearby Share), "
            "KDE Connect (Phone Link — SMS, ring phone, cross-device clipboard), and Dynamic Lock (trusted phone locks PC). "
            "No terminal needed."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        for label, desc in (
            ("Nearby Share", "LocalSend — send files to any nearby PC/phone via QR, no cloud. Same as Quick Share on Windows."),
            ("Phone Link", "KDE Connect — pair phone for SMS, ring phone, cross-device clipboard, and file drop."),
            ("Dynamic Lock", "Walk away and PC locks via Bluetooth phone proximity — kyth-dynamic-lock.service."),
        ):
            row = QHBoxLayout()
            row.setSpacing(10)
            l = QLabel(label)
            l.setObjectName("card-subtitle")
            l.setMinimumWidth(130)
            row.addWidget(l)
            d = QLabel(desc)
            d.setObjectName("card-copy")
            d.setWordWrap(True)
            row.addWidget(d, 1)
            layout.addLayout(row)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        nearby_btn = QPushButton("Open LocalSend")
        nearby_btn.setToolTip("Launch LocalSend for Nearby Share")
        try:
            from ..services.launch import popen
            nearby_btn.clicked.connect(lambda _=False: popen(["flatpak","run","org.localsend.localsend_app"]))
        except Exception:
            pass
        btns.addWidget(nearby_btn)
        phone_btn = QPushButton("KDE Connect Settings")
        phone_btn.clicked.connect(lambda _=False: __import__("kyth_welcome.services.launch", fromlist=["popen"]).popen(["kcmshell6","kcm_kdeconnect"]) if True else None)
        btns.addWidget(phone_btn)
        btns.addStretch()
        layout.addLayout(btns)
        self._add(card)
