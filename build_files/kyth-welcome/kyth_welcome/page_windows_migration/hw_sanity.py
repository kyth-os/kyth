"""Windows Migration page — hardware sanity check card + handlers, _HwSanityMixin."""

from __future__ import annotations

from ..services.runtime import DataWorker, release_worker_when_finished
from ..services.windows_migration import (
    _collect_hw_sanity,
)
from ..qt import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, single_shot,
)
from ..widgets import (
    _make_card,
)


class _HwSanityMixin:
    def _build_hw_card(self):
        # Hardware sanity — the things the previous setup configured silently
        hw_card, hw_layout = _make_card()
        hw_top = QHBoxLayout()
        hw_title = QLabel("Did everything come along? Quick hardware check")
        hw_title.setObjectName("card-title")
        hw_top.addWidget(hw_title)
        hw_top.addStretch()
        hw_again_btn = QPushButton("Check Again")
        hw_again_btn.clicked.connect(self._run_hw_sanity)
        hw_top.addWidget(hw_again_btn)
        hw_layout.addLayout(hw_top)
        hw_body = QLabel(
            "Network, display (HDR and variable refresh), printers, Bluetooth, and power — "
            "the things Windows set up silently, checked here so you don't have to hunt for drivers."
        )
        hw_body.setObjectName("card-copy")
        hw_body.setWordWrap(True)
        hw_layout.addWidget(hw_body)
        self._hw_status = QLabel("Checking…")
        self._hw_status.setObjectName("card-copy")
        hw_layout.addWidget(self._hw_status)
        self._hw_rows = QVBoxLayout()
        self._hw_rows.setSpacing(6)
        hw_layout.addLayout(self._hw_rows)
        hw_btns = QHBoxLayout()
        hw_btns.setSpacing(8)
        self._hw_printer_btn = QPushButton("Set Up Printer")
        self._hw_printer_btn.setToolTip("Runs: ujust setup-printer")
        self._hw_printer_btn.hide()
        self._hw_printer_btn.clicked.connect(
            lambda _=False: self._run_ujust("setup-printer", self._hw_printer_btn))
        hw_btns.addWidget(self._hw_printer_btn)
        hw_open_btn = QPushButton("Open Hardware")
        hw_open_btn.clicked.connect(lambda _=False: self._navigate("Hardware"))
        hw_btns.addWidget(hw_open_btn)
        hw_btns.addStretch()
        hw_layout.addLayout(hw_btns)
        self._add(hw_card)
        # Pages are built eagerly at startup; defer the subprocess probes.
        single_shot(self, 900, self._run_hw_sanity)

    def _run_hw_sanity(self):
        if self._hw_worker is not None and self._hw_worker.isRunning():
            return
        self._hw_status.setText("Checking…")
        self._hw_status.show()
        worker = DataWorker("hw-sanity", _collect_hw_sanity)
        worker.result.connect(self._on_hw_sanity)
        self._hw_worker = worker
        release_worker_when_finished(self, "_hw_worker", worker)
        worker.start()

    def _on_hw_sanity(self, _key: str, rows: list):
        self._clear_layout(self._hw_rows)
        if not rows:
            self._hw_status.setText("Could not run the hardware checks in this session.")
            return
        self._hw_status.hide()
        printer_missing = False
        for status, title, text in rows:
            if title == "Printer" and status == "warn":
                printer_missing = True
            self._hw_rows.addWidget(self._make_migration_row(status, title, text))
        self._hw_printer_btn.setVisible(printer_missing)
