"""Game Boost card for PerformancePage."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .page_performance import PerformancePage


def make_game_boost_card(page: "PerformancePage"):
    from .widgets import _make_card
    from .qt import QLabel, QPushButton, QHBoxLayout, QCheckBox, QComboBox

    card, layout = _make_card("card-accent-ok")
    title = QLabel("Game Boost — one switch for latency, scheduler, overlay")
    title.setObjectName("card-title")
    layout.addWidget(title)
    body = QLabel(
        "Like Windows Game Mode: scx scheduler (scx_rusty/lavd), MangoHud overlay (Right Shift+F12), "
        "and KWin low-latency compositor. Apply together as Game Night, copy launch options as one line."
    )
    body.setObjectName("card-copy")
    body.setWordWrap(True)
    layout.addWidget(body)
    row = QHBoxLayout()
    row.setSpacing(8)
    page._boost_sched_combo = QComboBox()
    page._boost_sched_combo.addItems(["scx_rusty", "scx_lavd", "scx_bpfland"])
    row.addWidget(page._boost_sched_combo)
    page._boost_mh_check = QCheckBox("MangoHud")
    page._boost_mh_check.setChecked(True)
    row.addWidget(page._boost_mh_check)
    page._boost_latency_check = QCheckBox("Low latency")
    page._boost_latency_check.setChecked(True)
    row.addWidget(page._boost_latency_check)
    layout.addLayout(row)
    btns = QHBoxLayout()
    btns.setSpacing(8)
    apply_btn = QPushButton("Apply Game Night")
    apply_btn.setObjectName("primary")
    apply_btn.clicked.connect(page._apply_game_boost)
    btns.addWidget(apply_btn)
    copy_btn = QPushButton("Copy Launch Options")
    from kyth_welcome.widgets import _copy_text as _gb_copy

    copy_btn.clicked.connect(lambda _=False: _gb_copy("MANGOHUD=1 %command%"))
    btns.addWidget(copy_btn)
    btns.addStretch()
    layout.addLayout(btns)
    page._boost_status = QLabel("Ready to boost — scx + overlay + latency in one click.")
    page._boost_status.setObjectName("card-copy")
    page._boost_status.setWordWrap(True)
    layout.addWidget(page._boost_status)
    return card
