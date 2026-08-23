"""Shared card/section helpers — extracted from widgets/__init__.py 770-LOC monolith.

Windows Settings density without bento: plain QFrame#card, 2-col grid.
"""
from __future__ import annotations

from ..qt import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget, Qt


def _make_card(name: str = "card") -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName(name)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(8)
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


def _make_setting_row(title: str, subtitle: str, control: QWidget) -> QFrame:
    """One row inside a settings card: name (+ optional one-line
    description) on the left, a single trailing control — a ToggleSwitch,
    a PillBadge, a button — on the right. The Windows-Settings list-row
    shape, shared so pages stop hand-rolling their own QHBoxLayout around a
    bare QCheckBox for every on/off setting."""
    row = QFrame()
    row.setObjectName("setting-row")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 8, 0, 8)
    layout.setSpacing(16)

    text_col = QVBoxLayout()
    text_col.setSpacing(2)
    title_lbl = QLabel(title)
    title_lbl.setObjectName("setting-row-title")
    title_lbl.setWordWrap(True)
    text_col.addWidget(title_lbl)
    if subtitle:
        sub_lbl = QLabel(subtitle)
        sub_lbl.setObjectName("setting-row-subtitle")
        sub_lbl.setWordWrap(True)
        text_col.addWidget(sub_lbl)
    layout.addLayout(text_col, 1)
    layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    return row


def _divider() -> QFrame:
    f = QFrame()
    f.setObjectName("divider")
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    return f
