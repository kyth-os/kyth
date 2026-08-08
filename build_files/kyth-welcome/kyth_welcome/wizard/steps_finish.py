"""Wizard step builder — _FinishStepMixin."""
from __future__ import annotations

from ..qt import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from ..services.launch import flatpak_run
from ..services.setup_state import STEP_LABELS, load_state, relevant_steps
from ..widgets import _make_card

_CHIP_OBJECT_NAME = {
    "done": "wiz-chip-done",
    "skipped": "wiz-chip-skipped",
    "pending": "wiz-chip-pending",
}
_CHIP_TEXT = {
    "done": "Done",
    "skipped": "Skipped",
    "pending": "Not started",
}


class _FinishStepMixin:
    def _make_status_card(self) -> QWidget:
        card, layout = _make_card("wiz-card")
        title = QLabel("Setup summary")
        title.setObjectName("wiz-card-title")
        layout.addWidget(title)

        self._finish_rows_layout = QVBoxLayout()
        self._finish_rows_layout.setSpacing(10)
        layout.addLayout(self._finish_rows_layout)
        return card

    def _refresh_finish_status(self) -> None:
        """Called each time the Finish step becomes current. Rebuilds the row
        set (not just chip text) — which steps even apply depends on profile,
        and profile can change after this card was first built (Welcome ->
        back -> different profile -> forward again)."""
        rows_layout = getattr(self, "_finish_rows_layout", None)
        if rows_layout is None:
            return
        while rows_layout.count():
            item = rows_layout.takeAt(0)
            sub = item.layout()
            if sub is not None:
                while sub.count():
                    sub_item = sub.takeAt(0)
                    sub_widget = sub_item.widget()
                    if sub_widget is not None:
                        sub_widget.setParent(None)
                        sub_widget.deleteLater()

        state = load_state()
        for key in relevant_steps(self._profile):
            row = QHBoxLayout()
            row.setSpacing(10)
            name = QLabel(STEP_LABELS.get(key, key))
            name.setObjectName("wiz-card-copy")
            row.addWidget(name, 1)
            status = state.get(key, "pending")
            chip = QLabel(_CHIP_TEXT.get(status, "Not started"))
            chip.setObjectName(_CHIP_OBJECT_NAME.get(status, "wiz-chip-pending"))
            row.addWidget(chip)
            rows_layout.addLayout(row)

    def _make_finish_step(self) -> QWidget:
        page = QWidget()
        page.setObjectName("wiz-body")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(72, 0, 72, 0)
        layout.setSpacing(0)
        layout.addStretch()

        check = QLabel("✓")
        check.setObjectName("glyph-finish-ok")
        layout.addWidget(check)
        layout.addSpacing(18)

        title = QLabel("You're all set.")
        title.setObjectName("finish-title")
        layout.addWidget(title)
        layout.addSpacing(10)

        subtitle = QLabel(
            "Open Steam, go to Settings → Compatibility, and enable Proton for all titles.\n"
            "Your full game library will appear and be ready to install.\n\n"
            "If an update makes games worse, open System Hub → Update and use Roll Back "
            "before reinstalling anything. The System Hub is always available from the app menu."
        )
        subtitle.setObjectName("finish-subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(24)

        layout.addWidget(self._make_status_card())
        layout.addSpacing(24)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        steam_btn = QPushButton("Open Steam")
        steam_btn.setObjectName("primary")
        steam_btn.clicked.connect(lambda: flatpak_run("com.valvesoftware.Steam"))
        btn_row.addWidget(steam_btn)
        self._finish_work_btn = QPushButton("Open Work Setup")
        self._finish_work_btn.setToolTip(
            "Office apps, Microsoft 365 shortcuts, document fonts, VPN, shares, and printing."
        )
        self._finish_work_btn.clicked.connect(lambda: self._open_hub_at("Work Setup"))
        self._finish_work_btn.setVisible(self._profile == "everyday")
        btn_row.addWidget(self._finish_work_btn)
        hub_btn = QPushButton("Open System Hub")
        hub_btn.clicked.connect(lambda: (self._next_btn.click() or None))
        btn_row.addWidget(hub_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch()
        return page
