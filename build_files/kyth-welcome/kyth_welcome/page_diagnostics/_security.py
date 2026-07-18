# __KYTH_GENERATED_IMPORTS__
from ..core_base import _release_worker_when_finished
from ..services.diagnostics import _collect_security_status
from ..services.gaming import DataWorker
from ..qt import QHBoxLayout, QLabel, QVBoxLayout
from ..widgets import _make_card


class _SecurityMixin:
    def _make_security_card(self) -> QFrame:
        from ..qt import QFrame
        card, layout = _make_card()
        title = QLabel("Security at a glance")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "The Security checklist, KythOS edition \u2014 what protects this "
            "PC and whether it's active right now."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        self._security_rows = QVBoxLayout()
        self._security_rows.setSpacing(6)
        layout.addLayout(self._security_rows)

        worker = DataWorker("security", _collect_security_status)
        worker.result.connect(self._on_security_status)
        self._security_worker = worker
        _release_worker_when_finished(self, "_security_worker", worker)
        worker.start()
        return card

    def _on_security_status(self, _key: str, rows: list):
        glyphs = {"ok": "\u2713", "warn": "!", "dim": "\u00b7"}
        styles = {"ok": "status-ok", "warn": "status-warn", "dim": "status-dim"}
        for status, area, text in rows:
            row = QHBoxLayout()
            row.setSpacing(10)
            mark = QLabel(glyphs.get(status, "\u00b7"))
            mark.setObjectName(styles.get(status, "status-dim"))
            mark.setFixedWidth(16)
            row.addWidget(mark)
            area_lbl = QLabel(area)
            area_lbl.setObjectName("card-summary")
            area_lbl.setMinimumWidth(110)
            row.addWidget(area_lbl)
            text_lbl = QLabel(text)
            text_lbl.setObjectName("card-copy")
            text_lbl.setWordWrap(True)
            row.addWidget(text_lbl, 1)
            self._security_rows.addLayout(row)
