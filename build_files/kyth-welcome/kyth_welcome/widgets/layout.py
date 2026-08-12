"""FlowLayout + HubPage — extracted helpers for Mission Central.

FlowLayout: wrap layout. HubPage: structured page base that enforces the
Mission Central template (header → primary grid → disclosure → log drawer)
while keeping per-page business logic owned by callers.
"""

from ..qt import QLabel, QLayout, QRect, QSize, Qt, QVBoxLayout, QWidget

from .cards import _divider, _make_card, _make_grid, _make_section_header


class FlowLayout(QLayout):
    """Left-to-right wrap layout — see widgets.py docstring."""

    def __init__(self, parent=None, margin: int = 0, spacing: int = 8):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items: list = []
        self._cached_size_hint: QSize | None = None
        self._cached_min_size: QSize | None = None
        self._cached_width: int | None = None
        self._cached_height: int | None = None

    def addItem(self, item):
        self._items.append(item)
        self._cached_size_hint = None
        self._cached_min_size = None
        self._cached_width = None

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        self._cached_size_hint = None
        self._cached_min_size = None
        self._cached_width = None
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        if self._cached_width == width and self._cached_height is not None:
            return self._cached_height
        height = self._do_layout(QRect(0, 0, width, 0), test_only=True)
        self._cached_width = width
        self._cached_height = height
        return height

    def setGeometry(self, rect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        if self._cached_size_hint is not None:
            return self._cached_size_hint
        self._cached_size_hint = self.minimumSize()
        return self._cached_size_hint

    def minimumSize(self):
        if self._cached_min_size is not None:
            return self._cached_min_size
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        self._cached_min_size = size
        return size

    def _do_layout(self, rect, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        x, y = effective.x(), effective.y()
        line_height = 0
        spacing = self.spacing()
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > effective.right() and line_height > 0:
                x = effective.x()
                y += line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(x, y, hint.width(), hint.height()))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + bottom


class HubPage(QWidget):
    """Structured base for Mission Central pages.

    Thin wrapper over the existing Page scroll pattern, but with named
    helpers that enforce the template: header → section → 2-col grid →
    disclosure row → log drawer. Existing Page subclasses can migrate
    incrementally; new pages should inherit HubPage directly.
    """

    def __init__(self):
        super().__init__()
        self.setObjectName("content-area")
        from ..qt import QFrame, QScrollArea

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._outer = outer

        # Scroll container mirrors Page's _NoAutoScrollArea contract
        # but without importing the private class (keep layout.py standalone).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        container = QWidget()
        container.setObjectName("content-area")
        scroll.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(48, 34, 56, 42)
        layout.setSpacing(18)
        self._layout = layout

    # Re-expose Page API so callers can migrate without rewiring
    def _page_header(self, eyebrow: str, title: str, subtitle: str = "") -> None:
        hdr = QWidget()
        hdr.setObjectName("page-header")
        hdr_layout = QVBoxLayout(hdr)
        hdr_layout.setContentsMargins(48, 26, 56, 18)
        hdr_layout.setSpacing(7)
        ew = QLabel(eyebrow.upper())
        ew.setObjectName("eyebrow")
        hdr_layout.addWidget(ew)
        ttl = QLabel(title)
        ttl.setObjectName("heading")
        hdr_layout.addWidget(ttl)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("subheading")
            sub.setWordWrap(True)
            hdr_layout.addWidget(sub)
        self._outer.insertWidget(0, hdr)
        self._outer.insertWidget(1, _divider())

    def _add(self, widget: QWidget) -> QWidget:
        self._layout.addWidget(widget)
        return widget

    def _add_layout(self, layout) -> None:
        self._layout.addLayout(layout)

    def _stretch(self):
        self._layout.addStretch()

    def section(self, title: str, subtitle: str = "") -> QVBoxLayout:
        """Add a Windows-Settings-style section header and return its layout for callers."""
        frame, layout = _make_section_header(title, subtitle)
        self._add(frame)
        return layout

    def grid(self) -> QVBoxLayout:
        """Create a 2-col card grid attached to this page."""

        return _make_grid(self._layout)

    def card(self, name: str = "card"):
        return _make_card(name)
