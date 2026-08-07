"""FlowLayout — extract from widgets.py god module (R8-3).

Single reusable layout that wraps to a new row. Keep Qt import local so
`import kyth_welcome.widgets` cold path does not pay for it until needed.
"""

from ..qt import QLayout, QRect, QSize, Qt


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
