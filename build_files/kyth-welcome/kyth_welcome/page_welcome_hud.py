"""Welcome HUD — HUD grid, split from page_welcome.py 745 (R7)."""
from __future__ import annotations

from .qt import QFrame, QGridLayout, QLabel, QPushButton, QVBoxLayout, Qt


class _WelcomeHudMixin:
    """HUD grid helpers. QSS via objectName, no inline setStyleSheet."""

    def _new_card(self, object_name: str, *, margins=(18, 16, 18, 16), spacing=8) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName(object_name)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        return card, layout

    def _make_card_header(self, title_text: str, layout: QVBoxLayout) -> None:
        title = QLabel(title_text)
        title.setObjectName("hud-title")
        layout.addWidget(title)

    def _make_hud_card(
        self,
        title_text: str,
        body_text: str,
        grid: QGridLayout,
        row: int,
        col: int,
    ) -> QLabel:
        card, card_layout = self._new_card("genz-hud-card")
        self._make_card_header(title_text, card_layout)
        desc = QLabel(body_text)
        desc.setTextFormat(Qt.TextFormat.RichText)
        desc.setObjectName("hud-desc")
        desc.setWordWrap(True)
        card_layout.addWidget(desc)
        grid.addWidget(card, row, col)
        return desc

    def _make_action_hud_card(
        self,
        title_text: str,
        body_text: str,
        button_text: str,
        callback,
        grid: QGridLayout,
        row: int,
        col: int,
    ) -> tuple[QLabel, QPushButton]:
        card, card_layout = self._new_card("genz-hud-card")
        self._make_card_header(title_text, card_layout)
        desc = QLabel(body_text)
        desc.setObjectName("hud-desc")
        desc.setWordWrap(True)
        card_layout.addWidget(desc)
        btn = QPushButton(button_text)
        btn.setObjectName("primary")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _=False: callback())
        card_layout.addWidget(btn)
        grid.addWidget(card, row, col)
        return desc, btn

    def _make_hud_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(12)

        self._hud1_desc = self._make_hud_card(
            "SYSTEM NODE",
            f"<b>Device:</b> {self._hostname}<br>"
            f"<b>Kernel:</b> {self._kernel}<br>"
            f"<b>Channel:</b> {self._facts['branch']}",
            grid,
            0,
            0,
        )
        self._hud2_desc = self._make_hud_card(
            "ENVIRONMENT",
            f"<b>Session Type:</b> {self._session}<br>"
            f"<b>Audio Engine:</b> PipeWire ({self._facts['pipewire'].strip()})<br>"
            f"<b>Desktop Portal:</b> {self._facts['portal'].strip()}",
            grid,
            0,
            1,
        )
        self._hud3_desc = self._make_hud_card(
            "RECOVERY & DUAL-BOOT",
            f"<b>Previous State:</b> {'Available' if self._facts['rollback'] else 'None'}<br>"
            f"<b>Windows Disk:</b> {'Detected' if self._facts['windows_found'] else 'Not Detected'}<br>"
            f"<b>Fallback Theme:</b> Verified",
            grid,
            1,
            0,
        )
        self._hud4_desc, self._hud4_btn = self._make_action_hud_card(
            "RECOMMENDED ACTIONS",
            self._hero_view.rec_text,
            self._hero_view.rec_btn_label,
            self._on_recommended_action,
            grid,
            1,
            1,
        )
        return grid
