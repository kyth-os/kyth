"""Shared card/section helpers — extracted from widgets/__init__.py 770-LOC monolith.

Windows Settings density without bento: plain QFrame#card, 2-col grid.
"""
from __future__ import annotations

from ..qt import QFrame, QGridLayout, QLabel, QVBoxLayout


def _make_card(name: str = "card") -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName(name)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(10)
    return card, layout


def _make_section_header(title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    """Windows Settings-style section header — title 15/700, subtitle 12/muted."""
    frame = QFrame()
    frame.setObjectName("section-header")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(2, 14, 2, 6)
    layout.setSpacing(4)
    t = QLabel(title)
    t.setObjectName("section-title")
    layout.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("section-subtitle")
        s.setWordWrap(True)
        layout.addWidget(s)
    return frame, layout


def _make_grid(container: QVBoxLayout) -> QGridLayout:
    """2-col responsive grid for cards."""
    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(12)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    container.addLayout(grid)
    return grid


def _divider() -> QFrame:
    f = QFrame()
    f.setObjectName("divider")
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    return f
