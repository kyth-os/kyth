"""Welcome HUD — HUD grid, split from page_welcome.py 737 (R7)."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout

class _WelcomeHudMixin:
    """HUD grid. Windows 11 Settings-like density: 2-col, 12px gap, QSS via objectName."""
    def _make_hud_grid(self):
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        return grid

    def _make_hud_card(self, title: str, value: str, status: str = "ok"):
        card = QFrame()
        card.setObjectName(f"hudCard-{status}")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("hudCardTitle")
        layout.addWidget(title_lbl)
        value_lbl = QLabel(value)
        value_lbl.setObjectName("hudCardValue")
        value_lbl.setWordWrap(True)
        layout.addWidget(value_lbl)
        return card
