# __KYTH_GENERATED_IMPORTS__
from ..actions import _install_flatpak_inline
from ..services.flatpak import _is_flatpak_installed
from ..services.work import _WORK_APPS
from ..qt import QHBoxLayout, QLabel, QPushButton
from ..widgets import _make_card


class _WorkAppsMixin:
    def _make_work_apps_card(self):
        card, layout = _make_card()
        title = QLabel("1. Office and email apps")
        title.setObjectName("card-title")
        layout.addWidget(title)
        copy = QLabel(
            "LibreOffice covers Word, Excel, and PowerPoint files. Betterbird handles "
            "work email and calendars. Both install from Flathub in one click."
        )
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        layout.addWidget(copy)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        for app_id, name, desc in _WORK_APPS:
            btn = QPushButton(f"Install {name}")
            btn.setToolTip(desc)
            if _is_flatpak_installed(app_id):
                btn.setText(f"\u2713 {name} installed")
                btn.setEnabled(False)
            else:
                btn.setObjectName("primary")
                btn.clicked.connect(
                    lambda _=False, b=btn, a=app_id, n=name: _install_flatpak_inline(self, b, a, n)
                )
            btns.addWidget(btn)
        btns.addStretch()
        layout.addLayout(btns)
        return card
