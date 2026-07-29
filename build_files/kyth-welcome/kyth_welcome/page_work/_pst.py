import os

# __KYTH_GENERATED_IMPORTS__
from ..services.runtime import release_worker_when_finished
from ..services.gaming import DataWorker
from ..services.work import _convert_pst, _scan_for_pst_files
from ..qt import QFileDialog, QHBoxLayout, QLabel, QPushButton
from ..widgets import _make_card


class _PstMixin:
    def _make_pst_card(self):
        card, layout = _make_card()
        title = QLabel("4. Outlook archives \u2014 bring your old email (.pst)")
        title.setObjectName("card-title")
        layout.addWidget(title)
        copy = QLabel(
            "Years of mail live in Outlook .pst archive files that nothing on Linux opens "
            "directly. KythOS converts them to the standard mbox format: in Betterbird, "
            "add the ImportExportTools NG add-on, then Tools \u2192 ImportExportTools NG \u2192 "
            "Import mbox file and pick the converted folder."
        )
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        layout.addWidget(copy)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self._pst_scan_btn = QPushButton("Find PST Files")
        self._pst_scan_btn.setObjectName("primary")
        self._pst_scan_btn.setToolTip("Scans mounted PC drives and your home folder for Outlook archives.")
        self._pst_scan_btn.clicked.connect(self._scan_pst)
        btns.addWidget(self._pst_scan_btn)
        pick_btn = QPushButton("Choose PST File\u2026")
        pick_btn.clicked.connect(self._pick_pst)
        btns.addWidget(pick_btn)
        btns.addStretch()
        layout.addLayout(btns)

        self._pst_status = QLabel("")
        self._pst_status.setObjectName("card-copy")
        self._pst_status.setWordWrap(True)
        self._pst_status.hide()
        layout.addWidget(self._pst_status)
        self._pst_found_row = QHBoxLayout()
        self._pst_found_row.setSpacing(8)
        layout.addLayout(self._pst_found_row)
        return card

    def _set_pst_status(self, text: str):
        self._pst_status.setText(text)
        self._pst_status.show()

    def _scan_pst(self):
        if self._pst_worker is not None and self._pst_worker.isRunning():
            return
        self._pst_scan_btn.setEnabled(False)
        self._set_pst_status("Scanning for Outlook archives\u2026")
        worker = DataWorker("pst-scan", _scan_for_pst_files)
        worker.result.connect(self._on_pst_found)
        self._pst_worker = worker
        release_worker_when_finished(self, "_pst_worker", worker)
        worker.start()

    def _on_pst_found(self, _key: str, paths: list):
        self._pst_scan_btn.setEnabled(True)
        while self._pst_found_row.count():
            item = self._pst_found_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not paths:
            self._set_pst_status(
                "No .pst files found. If your PC drive is not mounted yet, "
                "scan and unlock it from the Move Files page first, or "
                "use Choose PST File."
            )
            return
        self._set_pst_status(f"Found {len(paths)} archive{'s' if len(paths) != 1 else ''} \u2014 click one to convert:")
        for path in paths[:6]:
            btn = QPushButton(os.path.basename(path))
            btn.setToolTip(path)
            btn.clicked.connect(lambda _=False, p=path: self._convert_pst(p))
            self._pst_found_row.addWidget(btn)
        self._pst_found_row.addStretch()

    def _pick_pst(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose an Outlook archive", os.path.expanduser("~"),
            "Outlook archives (*.pst *.ost);;All files (*)",
        )
        if path:
            self._convert_pst(path)

    def _convert_pst(self, path: str):
        if self._pst_worker is not None and self._pst_worker.isRunning():
            return
        self._set_pst_status(f"Converting {os.path.basename(path)} \u2014 large archives can take a while\u2026")
        worker = DataWorker("pst-convert", lambda: _convert_pst(path))
        worker.result.connect(self._on_pst_converted)
        self._pst_worker = worker
        release_worker_when_finished(self, "_pst_worker", worker)
        worker.start()

    def _on_pst_converted(self, _key: str, result: tuple):
        ok, detail = result
        if ok:
            self._set_pst_status(
                f"\u2713 Converted to {detail}. In Betterbird: add the ImportExportTools NG "
                "add-on, then Tools \u2192 ImportExportTools NG \u2192 Import mbox file."
            )
        else:
            self._set_pst_status(f"\u2717 Conversion failed: {detail}")
