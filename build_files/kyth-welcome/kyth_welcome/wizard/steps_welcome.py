"""Wizard step builder — _WelcomeStepMixin ("Welcome" / profile pick).

System-check content (stats bar, preflight warnings) lives in
steps_machine.py's "Your Machine" step — this step is deliberately just the
hero and the profile choice that everything downstream adapts to.
"""
from __future__ import annotations

from ..qt import QHBoxLayout, QLabel, QVBoxLayout, QWidget, Qt
from ..widgets import _divider


class _ProfileCard(QWidget):
    """Clickable profile card: bold name + muted description, exclusive-select."""

    def __init__(self, key: str, name: str, desc: str, on_click):
        super().__init__()
        self._key = key
        self._checked = False
        self._on_click = on_click
        self.setObjectName("wiz-profile-card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(96)
        # Plain QWidget subclasses don't paint QSS background/border by
        # default (only QFrame and a few widgets do) — without this, the
        # card's background/border/[checked] styling silently never renders.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(6)

        self._name_lbl = QLabel(name)
        self._name_lbl.setObjectName("wiz-card-title")
        layout.addWidget(self._name_lbl)

        desc_lbl = QLabel(desc)
        desc_lbl.setObjectName("wiz-card-copy")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)
        layout.addStretch()

    def mousePressEvent(self, event):  # noqa: N802
        self._on_click(self._key)
        super().mousePressEvent(event)

    def set_checked(self, checked: bool) -> None:
        self._checked = checked
        self.setProperty("checked", checked)
        self.style().unpolish(self)
        self.style().polish(self)


class _WelcomeStepMixin:
    def _make_welcome_step(self) -> QWidget:
        page = QWidget()
        page.setObjectName("wiz-body")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        hero = QWidget()
        hero.setObjectName("wiz-body")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(52, 48, 52, 40)
        hero_layout.setSpacing(14)
        hero_layout.addStretch(1)

        pill = QLabel("KYTHOS FIRST BOOT SETUP")
        pill.setObjectName("wiz-pill")
        hero_layout.addWidget(pill)

        heading = QLabel("What's this machine for?")
        heading.setObjectName("wiz-heading")
        hero_layout.addWidget(heading)

        sub = QLabel(
            "This decides what the rest of setup shows you. You can always change it "
            "later from System Hub."
        )
        sub.setObjectName("wiz-subheading")
        sub.setWordWrap(True)
        hero_layout.addWidget(sub)

        hero_layout.addSpacing(8)

        self._profile_cards: dict[str, _ProfileCard] = {}
        profile_grid = QHBoxLayout()
        profile_grid.setSpacing(14)
        for key, name, desc in (
            ("everyday", "Everyday", "Browser, office, files, and a system that stays out of your way."),
            ("gaming", "Gaming", "Steam, Proton tuning, and launcher setup added to the path."),
        ):
            card = _ProfileCard(key, name, desc, self._on_profile_chosen)
            self._profile_cards[key] = card
            profile_grid.addWidget(card, 1)
        hero_layout.addLayout(profile_grid)
        self._profile_cards[self._profile].set_checked(True)

        hero_layout.addStretch(2)
        outer.addWidget(hero, 1)
        outer.addWidget(_divider())
        return page
