"""Welcome hero — hero/banner + vibe, split from page_welcome.py 745 (R7)."""
from __future__ import annotations

from .qt import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget, Qt


class _WelcomeHeroMixin:
    """Hero/banner + vibe helpers. QSS via objectName, no inline setStyleSheet."""

    def _make_hero_banner(self, hero_view) -> QFrame:
        card = QFrame()
        card.setObjectName("genz-hero")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        hero_text_col = QVBoxLayout()
        hero_text_col.setSpacing(4)

        title = QLabel("KYTHOS WORKSTATION")
        title.setObjectName("genz-hero-title")
        hero_text_col.addWidget(title)

        subtitle = QLabel("Atomic immutable (bootc) — instant updates & one-click rollback. Gaming + productivity, ready for Windows switchers.")
        subtitle.setObjectName("genz-hero-subtitle")
        subtitle.setWordWrap(True)
        hero_text_col.addWidget(subtitle)

        layout.addLayout(hero_text_col, 1)

        status_pill = QLabel()
        status_pill.setText(hero_view.pill_text)
        status_pill.setObjectName(hero_view.pill_object_name)
        layout.addWidget(status_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        self._hero_pill = status_pill
        return card

    def _make_vibe_section(self) -> QWidget:
        section = QWidget()
        section.setObjectName("segmented-tab-row")
        layout = QHBoxLayout(section)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        label = QLabel("WORKSTATION MODE:")
        label.setObjectName("home-kicker")
        layout.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)

        self._focus_buttons = {}
        for key, text, tip in (
            ("everyday", "💻 Everyday", "Office, browser & creators. Atomic updates with instant rollback if an update misbehaves."),
            ("gaming", "🎮 Gaming Rig", "Peak performance, one toggle. Same atomic safety, plus Steam/Proton."),
        ):
            button = QPushButton(text)
            button.setObjectName("segmented-tab")
            button.setCheckable(True)
            button.setToolTip(tip)
            button.clicked.connect(lambda _=False, k=key: self._on_focus_chosen(k))
            self._focus_buttons[key] = button
            layout.addWidget(button)

        layout.addSpacing(12)

        self._apply_preset_btn = QPushButton("Apply Settings")
        self._apply_preset_btn.setObjectName("primary")
        self._apply_preset_btn.clicked.connect(lambda _=False: self._apply_role_preset())
        layout.addWidget(self._apply_preset_btn)

        self._preset_status = QLabel("Ready to tune.")
        self._preset_status.setObjectName("status-dim")
        layout.addWidget(self._preset_status, 1)

        self._focus_buttons[self._profile].setChecked(True)
        return section
