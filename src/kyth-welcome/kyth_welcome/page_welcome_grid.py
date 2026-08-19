"""Welcome grid — category/section helpers, split from page_welcome.py 745 (R7)."""
from __future__ import annotations


from .qt import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSize, QVBoxLayout, Qt

from .widgets import _theme_icon


class _WelcomeGridMixin:
    """Grid/category helpers. QSS via objectName, no inline setStyleSheet."""

    def _build_category_section(self) -> None:
        from .services.welcome import home_categories

        self._nvidia_at_build = self._facts["has_nvidia"]
        categories = home_categories(has_nvidia=self._nvidia_at_build)

        self._category_grid = QGridLayout()
        self._category_grid.setSpacing(12)
        self._category_cards = []
        for icon_names, glyph, title, tasks in categories:
            card = self._make_category_card(icon_names, glyph, title, tasks)
            self._category_cards.append((card, title == "Games"))

        self._relayout_categories(self._profile)
        self._category_grid.setColumnStretch(0, 1)
        self._category_grid.setColumnStretch(1, 1)
        self._add_layout(self._category_grid)

    def _make_section_header(self, title: str, subtitle: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("home-section")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 12, 0, 4)
        layout.setSpacing(4)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("home-section-title")
        layout.addWidget(title_lbl)

        subtitle_lbl = QLabel(subtitle)
        subtitle_lbl.setObjectName("home-section-copy")
        subtitle_lbl.setWordWrap(True)
        layout.addWidget(subtitle_lbl)
        return frame

    def _relayout_categories(self, profile: str):
        from .services.welcome import visible_category_indexes

        visible = []
        visible_indexes = set(visible_category_indexes(
            profile, [is_games for _card, is_games in self._category_cards]
        ))
        for index, (card, _is_games) in enumerate(self._category_cards):
            self._category_grid.removeWidget(card)
            wanted = index in visible_indexes
            card.setVisible(wanted)
            if wanted:
                visible.append(card)
        for i, card in enumerate(visible):
            self._category_grid.addWidget(card, i // 2, i % 2)

    def _make_category_card(
        self,
        icon_names: tuple[str, ...],
        glyph: str,
        title: str,
        tasks: list[tuple[str, str]],
    ) -> QFrame:
        # Keep ownership even when profile filtering removes a card before the
        # grid itself is attached to the page (notably the hidden Games card).
        card = QFrame(self)
        title_lower = title.lower()
        if "games" in title_lower:
            card.setObjectName("genz-category-gaming")
        elif "apps" in title_lower:
            card.setObjectName("genz-category-apps")
        elif "system" in title_lower:
            card.setObjectName("genz-category-system")
        elif "network" in title_lower:
            card.setObjectName("genz-category-network")
        else:
            card.setObjectName("genz-category-advanced")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        icon = _theme_icon(*icon_names)
        icon_lbl = QLabel()
        if icon.isNull():
            icon_lbl.setText(glyph)
            icon_lbl.setObjectName("home-action-icon")
        else:
            icon_lbl.setPixmap(icon.pixmap(QSize(32, 32)))
        icon_lbl.setFixedWidth(36)
        layout.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(6)

        first_key = tasks[0][1] if tasks else None
        title_btn = QPushButton(title.replace("&", "&&"))
        title_btn.setObjectName("genz-category-title")
        title_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if first_key:
            title_btn.clicked.connect(lambda _=False, k=first_key: self._navigate(k))
        text_col.addWidget(title_btn, 0, Qt.AlignmentFlag.AlignLeft)

        for label, key in tasks:
            link = QPushButton(f"➔  {label}")
            link.setObjectName("genz-task-link")
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.clicked.connect(lambda _=False, k=key: self._navigate(k))
            text_col.addWidget(link, 0, Qt.AlignmentFlag.AlignLeft)

        text_col.addStretch()
        layout.addLayout(text_col, 1)
        return card
