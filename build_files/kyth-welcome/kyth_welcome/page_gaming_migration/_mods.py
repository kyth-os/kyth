# __KYTH_GENERATED_IMPORTS__
from ..actions import _install_flatpak_inline
from ..qt import QDesktopServices, QHBoxLayout, QLabel, QPushButton, QUrl
from ..widgets import _make_card


class _ModsMixin:
    def _build_modding_migration_card(self):
        mods_card, mods_layout = _make_card()
        mods_title = QLabel("Mods \u2014 Nexus, MO2, SteamTinkerLaunch")
        mods_title.setObjectName("card-title")
        mods_layout.addWidget(mods_title)
        mods_desc = QLabel(
            "Start with Steam Workshop and native mod managers when a game provides "
            "them. For Bethesda-style load orders, use SteamTinkerLaunch to install "
            "Mod Organizer 2 per game; use Bottles for standalone patchers and tools."
        )
        mods_desc.setObjectName("card-copy")
        mods_desc.setWordWrap(True)
        mods_layout.addWidget(mods_desc)
        mods_btns = QHBoxLayout()
        mods_btns.setSpacing(8)
        protonup_btn = QPushButton("Open ProtonUp-Qt")
        protonup_btn.clicked.connect(lambda _=False: self._open_protonupqt())
        mods_btns.addWidget(protonup_btn)
        bottles_btn = QPushButton("Install Bottles")
        bottles_btn.clicked.connect(lambda _=False, b=bottles_btn: _install_flatpak_inline(
            self, b, "com.usebottles.bottles", "Bottles"))
        mods_btns.addWidget(bottles_btn)
        mods_doc_btn = QPushButton("Modding Guide")
        mods_doc_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/mrtrick37/kyth/blob/main/docs/modding-on-kythos.md")))
        mods_btns.addWidget(mods_doc_btn)
        mods_btns.addStretch()
        mods_layout.addLayout(mods_btns)
        self._add(mods_card)
