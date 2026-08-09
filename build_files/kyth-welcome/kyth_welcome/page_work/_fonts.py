# __KYTH_GENERATED_IMPORTS__
from ..services.runtime import Worker
from ..services.work import _ms_fonts_installed
from ..qt import QHBoxLayout, QLabel, QPushButton
from ..widgets import _make_card


class _FontsMixin:
    def _make_fonts_card(self):
        card, layout = _make_card()
        title = QLabel("3. Microsoft fonts \u2014 keep document formatting intact")
        title.setObjectName("card-title")
        layout.addWidget(title)
        copy = QLabel(
            "Documents from other PCs may use fonts like Times New Roman and Arial. "
            "Installing them keeps layouts pixel-identical instead of substituted."
        )
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        layout.addWidget(copy)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self._fonts_btn = QPushButton("Install Microsoft Fonts")
        if _ms_fonts_installed():
            self._fonts_btn.setText("\u2713 Microsoft fonts installed")
            self._fonts_btn.setEnabled(False)
        else:
            self._fonts_btn.setObjectName("primary")
        self._fonts_btn.clicked.connect(self._on_install_fonts)
        btns.addWidget(self._fonts_btn)
        btns.addStretch()
        layout.addLayout(btns)

        self._fonts_status = QLabel("")
        self._fonts_status.setObjectName("card-copy")
        self._fonts_status.setWordWrap(True)
        self._fonts_status.hide()
        layout.addWidget(self._fonts_status)
        return card

    def _on_install_fonts(self):
        if self._ms_fonts_worker is not None and self._ms_fonts_worker.isRunning():
            return
        self._fonts_btn.setEnabled(False)
        self._fonts_btn.setText("Installing\u2026")
        self._fonts_status.setText("Downloading Microsoft core fonts\u2026")
        self._fonts_status.show()
        self._ms_fonts_worker = Worker(["bash", "-c", "ujust install-ms-fonts"])
        self._ms_fonts_worker.finished.connect(lambda: setattr(self, "_ms_fonts_worker", None))
        self._ms_fonts_worker.finished.connect(self._ms_fonts_worker.deleteLater)
        self._ms_fonts_worker.done.connect(self._on_fonts_done)
        self._ms_fonts_worker.start()

    def _on_fonts_done(self, code: int):
        if code == 0:
            self._fonts_btn.setText("\u2713 Microsoft fonts installed")
            self._fonts_status.setText("\u2713 Done. Restart LibreOffice to pick up the new fonts.")
        else:
            self._fonts_btn.setEnabled(True)
            self._fonts_btn.setText("Install Microsoft Fonts")
            self._fonts_status.setText("\u2717 Installation failed. Check your network connection and try again.")
