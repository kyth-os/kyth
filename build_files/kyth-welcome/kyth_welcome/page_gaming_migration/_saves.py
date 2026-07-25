# __KYTH_GENERATED_IMPORTS__
from ..services.launch import flatpak_run
from ..actions import _install_flatpak_inline
from ..services.gaming import _ludusavi_backup_summary
from ..qt import QDesktopServices, QHBoxLayout, QLabel, QPushButton, QUrl
from ..widgets import _make_card


class _SavesMixin:
    def _build_save_backup_card(self):
        self._divider()
        saves_card, saves_layout = _make_card("card-accent-ok")
        saves_title = QLabel("Game Saves \u2014 Back Up Before You Switch")
        saves_title.setObjectName("card-title")
        saves_layout.addWidget(saves_title)
        saves_desc = QLabel(
            "KythOS recommends Ludusavi for game save backup and restore. Run it "
            "before a other system migration, after importing a library, and before "
            "large modding sessions."
        )
        saves_desc.setObjectName("card-copy")
        saves_desc.setWordWrap(True)
        saves_layout.addWidget(saves_desc)
        self._saves_status_lbl = QLabel("")
        self._saves_status_lbl.setObjectName("card-copy")
        self._saves_status_lbl.setWordWrap(True)
        saves_layout.addWidget(self._saves_status_lbl)
        saves_btns = QHBoxLayout()
        saves_btns.setSpacing(8)
        ludusavi_btn = QPushButton("Install Ludusavi")
        ludusavi_btn.clicked.connect(lambda _=False, b=ludusavi_btn: _install_flatpak_inline(
            self, b, "com.github.mtkennerly.ludusavi", "Ludusavi"))
        saves_btns.addWidget(ludusavi_btn)
        ludusavi_open_btn = QPushButton("Open Ludusavi")
        ludusavi_open_btn.clicked.connect(lambda _=False: flatpak_run("com.github.mtkennerly.ludusavi"))
        saves_btns.addWidget(ludusavi_open_btn)
        saves_refresh_btn = QPushButton("Refresh Status")
        saves_refresh_btn.clicked.connect(self._refresh_gaming_dashboard)
        saves_btns.addWidget(saves_refresh_btn)
        saves_doc_btn = QPushButton("Save Migration Checklist")
        saves_doc_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/mrtrick37/kyth/blob/main/docs/game-save-migration.md")))
        saves_btns.addWidget(saves_doc_btn)
        saves_btns.addStretch()
        saves_layout.addLayout(saves_btns)
        self._add(saves_card)

    def _refresh_save_status(self):
        if not hasattr(self, "_saves_status_lbl"):
            return
        self._saves_status_lbl.setText("Scanning save backup tools\u2026")
        self._start_data_worker("saves", _ludusavi_backup_summary)

    def _render_save_status(self, data):
        if not hasattr(self, "_saves_status_lbl") or not data:
            return
        status, title, summary = data
        prefix = {
            "ok": "Ready",
            "warn": "Needs setup",
            "err": "Needs fix",
            "dim": "Optional",
        }.get(status, "Optional")
        self._saves_status_lbl.setText(f"{prefix}: {title} - {summary}")
