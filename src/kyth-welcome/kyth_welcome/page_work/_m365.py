# __KYTH_GENERATED_IMPORTS__
from ..actions import _open_chromium_webapp
from ..services.work import _M365_APPS, _create_m365_shortcuts, _m365_shortcuts_present, _refresh_m365_shortcuts
from ..qt import QHBoxLayout, QLabel, QPushButton
from ..widgets import _make_card


class _M365Mixin:
    def _make_m365_card(self):
        card, layout = _make_card()
        title = QLabel("2. Microsoft 365 \u2014 web app shortcuts")
        title.setObjectName("card-title")
        layout.addWidget(title)
        copy = QLabel(
            "If your workplace uses Microsoft 365, the full suite runs in the browser. "
            "Add launcher shortcuts so Outlook, Teams, Word, and the rest open in their "
            "own windows from the app menu \u2014 pinnable to the taskbar like native apps."
        )
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        layout.addWidget(copy)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self._m365_btn = QPushButton("Add Microsoft 365 to App Launcher")
        _refresh_m365_shortcuts()
        if _m365_shortcuts_present():
            self._m365_btn.setText("\u2713 Shortcuts added \u2014 find them in the app menu")
            self._m365_btn.setEnabled(False)
        else:
            self._m365_btn.setObjectName("primary")
        self._m365_btn.clicked.connect(self._on_add_m365)
        btns.addWidget(self._m365_btn)

        for name, url, tip in _M365_APPS[:2]:
            open_btn = QPushButton(f"Open {name}")
            open_btn.setToolTip(f"{tip} \u2014 opens in a dedicated window")
            open_btn.clicked.connect(
                lambda _=False, u=url: _open_chromium_webapp(self, u)
            )
            btns.addWidget(open_btn)
        btns.addStretch()
        layout.addLayout(btns)
        return card

    def _on_add_m365(self):
        written = _create_m365_shortcuts()
        if written == len(_M365_APPS):
            self._m365_btn.setText("\u2713 Shortcuts added \u2014 find them in the app menu")
            self._m365_btn.setEnabled(False)
        else:
            self._m365_btn.setText(f"Added {written} of {len(_M365_APPS)} \u2014 try again")
