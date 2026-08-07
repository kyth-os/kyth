"""Welcome HUD — HUD grid, split from page_welcome.py 737 (R7)."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel
class _WelcomeHudMixin:
    """HUD grid. No inline styles, no identical 3-card lucide grid."""
    def _make_hud_grid(self):
        grid = QGridLayout()
        return grid
    def _make_hud_card(self, title: str, value: str):
        card = QFrame()
        card.setObjectName("hudCard")
        return card
