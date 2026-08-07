"""Welcome grid — category/section headers, split from page_welcome.py 737 (R7)."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout
class _WelcomeGridMixin:
    """Grid/category helpers. No inline styles — hierarchy via objectName + QSS."""
    def _make_section_header(self, title: str, subtitle: str = ""):
        frame = QFrame()
        frame.setObjectName("sectionHeader")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(2, 14, 2, 6)
        layout.setSpacing(4)
        t = QLabel(title)
        t.setObjectName("sectionTitle")
        layout.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("sectionSubtitle")
            s.setWordWrap(True)
            layout.addWidget(s)
        return frame

    def _make_category_card(self, title: str, subtitle: str, icon: str = ""):
        card = QFrame()
        card.setObjectName("categoryCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("categoryCardTitle")
        layout.addWidget(title_lbl)
        sub = QLabel(subtitle)
        sub.setObjectName("categoryCardSubtitle")
        sub.setWordWrap(True)
        layout.addWidget(sub)
        return card
