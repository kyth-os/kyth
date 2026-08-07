"""Welcome grid — category/section headers, split from page_welcome.py 737 (R7)."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout
class _WelcomeGridMixin:
    """Grid/category helpers. No inline styles — hierarchy via objectName + QSS."""
    def _make_section_header(self, title: str, subtitle: str = ""):
        frame = QFrame()
        frame.setObjectName("sectionHeader")
        layout = QVBoxLayout(frame)
        t = QLabel(title)
        t.setObjectName("sectionTitle")
        layout.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("sectionSubtitle")
            layout.addWidget(s)
        return frame
    def _make_category_card(self, title: str, subtitle: str, icon: str = ""):
        card = QFrame()
        card.setObjectName("categoryCard")
        return card
