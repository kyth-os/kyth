# __KYTH_GENERATED_IMPORTS__
from ..services.launch import kcmshell, systemsettings
from ..qt import QHBoxLayout, QLabel, QPushButton
from ..widgets import _make_card


class _ConnectMixin:
    def _make_connect_card(self):
        card, layout = _make_card()
        title = QLabel("6. Connect to your workplace")
        title.setObjectName("card-title")
        layout.addWidget(title)
        copy = QLabel(
            "Each of these opens the matching setup page. Have your IT details handy: "
            "VPN gateway address, share paths (\\\\server\\share), and printer name."
        )
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        layout.addWidget(copy)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        for label, page_key in (
            ("Set up VPN", "VPN"),
            ("Mount Network Shares", "Network Shares"),
            ("Sync Cloud Storage", "Cloud Storage"),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, k=page_key: self._navigate(k))
            btns.addWidget(btn)

        printer_btn = QPushButton("Add a Printer")
        printer_btn.setToolTip("Opens KDE printer settings. Network printers are usually detected automatically.")
        printer_btn.clicked.connect(self._open_printer_settings)
        btns.addWidget(printer_btn)
        btns.addStretch()
        layout.addLayout(btns)
        return card

    @staticmethod
    def _open_printer_settings():
        if not kcmshell("kcm_printer_manager"):
            systemsettings("kcm_printer_manager")
