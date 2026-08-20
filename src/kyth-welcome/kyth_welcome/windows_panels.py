"""Panel builders for Windows (System Hub shell) — search & mission bar."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .windows import Windows


def build_search_panel(window: "Windows", central_layout) -> None:
    from .qt import QFrame, QLabel, QVBoxLayout

    window._search_panel = QFrame()
    window._search_panel.setObjectName("search-results-panel")
    window._search_panel.hide()
    window._search_panel_layout = QVBoxLayout(window._search_panel)
    window._search_panel_layout.setContentsMargins(266, 12, 24, 14)
    window._search_panel_layout.setSpacing(8)

    window._search_results_title = QLabel("Search results")
    window._search_results_title.setObjectName("search-results-title")
    window._search_panel_layout.addWidget(window._search_results_title)

    window._search_results_body = QVBoxLayout()
    window._search_results_body.setSpacing(6)
    window._search_panel_layout.addLayout(window._search_results_body)

    window._search_results_hint = QLabel("")
    window._search_results_hint.setObjectName("search-results-hint")
    window._search_results_hint.setWordWrap(True)
    window._search_panel_layout.addWidget(window._search_results_hint)
    central_layout.addWidget(window._search_panel)


def build_mission_bar(window: "Windows", central_layout) -> None:
    from .qt import QHBoxLayout, QLabel, QWidget

    bar = QWidget()
    bar.setObjectName("mission-bar")
    bar.setFixedHeight(30)
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(254, 4, 14, 4)
    layout.setSpacing(8)

    kicker = QLabel("System")
    kicker.setObjectName("mission-kicker")
    layout.addWidget(kicker)

    sep = QLabel("·")
    sep.setObjectName("mission-sep")
    layout.addWidget(sep)

    window._mission_pills: list[QLabel] = []
    for _ in range(4):
        pill = QLabel("")
        pill.setObjectName("mission-pill-dim")
        pill.hide()
        layout.addWidget(pill)
        window._mission_pills.append(pill)

    layout.addStretch()

    from .qt import QPushButton, Qt as _Qt  # local to avoid circular

    window._mission_guardian_hint = QPushButton("")
    window._mission_guardian_hint.setObjectName("mission-pill-warn")
    window._mission_guardian_hint.setCursor(_Qt.CursorShape.PointingHandCursor)
    window._mission_guardian_hint.setFlat(True)
    window._mission_guardian_hint.hide()
    layout.addWidget(window._mission_guardian_hint)

    window._mission_ai_hint = QLabel("")
    window._mission_ai_hint.setObjectName("mission-kicker")
    window._mission_ai_hint.hide()
    layout.addWidget(window._mission_ai_hint)

    central_layout.addWidget(bar)
    window._mission_bar = bar
