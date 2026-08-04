import re
from typing import ClassVar

# __KYTH_GENERATED_IMPORTS__
from .core_base import restyle
from .services.hardware import HardwareProbe
from .qt import (
    QApplication, QFrame, QHBoxLayout, QIcon, QLabel, QLayout, QPushButton, QRect, QScrollArea, QSize, QSizePolicy, QTextEdit, QVBoxLayout, QWidget, Qt, Signal, single_shot,
)
from .ui_tokens import STATUS_ERROR, STATUS_OK, STATUS_WARN

def _theme_icon(*names: str) -> QIcon:
    """Return the first available system theme icon, or a null icon."""
    for name in names:
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            return icon
    return QIcon()


def _divider() -> QFrame:
    f = QFrame()
    f.setObjectName("divider")
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    return f


class FlowLayout(QLayout):
    """Left-to-right layout that wraps to a new row when it runs out of
    horizontal space, instead of overflowing past the window edge like
    QHBoxLayout does. Standard Qt "Flow Layout" recipe — Qt has no built-in
    equivalent. Use for button/chip rows whose item count varies or is too
    large to reliably fit one line (e.g. Repair's quick-fixes toolbar)."""

    def __init__(self, parent=None, margin: int = 0, spacing: int = 8):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items: list = []

    def addItem(self, item):
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
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


def _make_card(name: str = "card") -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName(name)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(24, 22, 24, 22)
    layout.setSpacing(12)
    return card, layout


class SegmentedTabBar(QFrame):
    """Shared row of checkable "segmented" buttons for sub-navigation within
    a page — Gaming's section switcher, the App Store's tab bar, and
    Compatibility's game-list filter all built this same row (checkable
    QPushButtons, one active at a time, syncing checked/objectName/restyle
    across the group) independently before this existed.

    This widget owns only the bar itself — what "activating a tab" *does*
    (build a panel, filter a list, whatever) stays entirely up to the
    caller via the `activated` signal. That keeps this reusable across
    pages whose content-switching semantics differ (lazily-built panels vs.
    filtering an already-built list) while still sharing the one thing that
    was actually identical: the button-row bookkeeping.
    """
    activated = Signal(object)  # emits the newly active tab's key

    def __init__(self, items: list[tuple[object, str]], *, active: object = None, kicker: str = ""):
        """items: (key, label) pairs in display order. key can be any
        hashable value (an int index, a string) — whatever the caller finds
        natural to switch on."""
        super().__init__()
        self.setObjectName("segmented-tab-row")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(8)

        if kicker:
            kicker_lbl = QLabel(kicker)
            kicker_lbl.setObjectName("home-kicker")
            layout.addWidget(kicker_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        self._buttons: dict[object, QPushButton] = {}
        self._active = active if active is not None else (items[0][0] if items else None)
        for key, label in items:
            btn = QPushButton(label)
            btn.setObjectName("segmented-tab")
            btn.setCheckable(True)
            btn.setChecked(key == self._active)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, k=key: self._on_clicked(k))
            layout.addWidget(btn)
            self._buttons[key] = btn
        layout.addStretch()

    def _on_clicked(self, key: object) -> None:
        # Always resync (even a re-click of the already-active tab) so the
        # bar can never end up with a button left unchecked because a
        # caller's activated handler no-ops on an unchanged key.
        self.set_active(key)
        self.activated.emit(key)

    def set_active(self, key: object) -> None:
        self._active = key
        for btn_key, btn in self._buttons.items():
            btn.setChecked(btn_key == key)
            restyle(btn)

    def button(self, key: object) -> QPushButton:
        return self._buttons[key]


def _launch_opt_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("launch-opt-label")
    lbl.setMinimumWidth(130)
    return lbl


def _launch_opt_value(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("launch-opt-value")
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lbl


def _copy_text(text: str):
    QApplication.clipboard().setText(text)


class StatusBadge(QLabel):
    """Compact shared status label for page and task feedback."""
    _STATE_NAMES: ClassVar[dict[str, str]] = {
        "idle": "task-status-idle",
        "running": "task-status-running",
        "ok": "task-status-ok",
        "warn": "task-status-warn",
        "err": "task-status-err",
    }

    def __init__(self, text: str = "", state: str = "idle"):
        super().__init__()
        self.setWordWrap(True)
        self.setMinimumWidth(220)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.set_state(state, text)

    def set_state(self, state: str, text: str) -> None:
        self.setText(text)
        self.setObjectName(self._STATE_NAMES.get(state, "task-status-idle"))
        restyle(self)


def status_color(state: str) -> str:
    return {
        "ok": STATUS_OK,
        "success": STATUS_OK,
        "warn": STATUS_WARN,
        "warning": STATUS_WARN,
        "error": STATUS_ERROR,
        "failed": STATUS_ERROR,
    }.get(state, STATUS_WARN)


class ActionRow(QFrame):
    """Shared horizontal command row with a trailing status badge."""
    def __init__(self, status_text: str = "", status_state: str = "idle"):
        super().__init__()
        self.setObjectName("action-row")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)
        self.status = StatusBadge(status_text, status_state)

    def add_button(self, text: str, callback=None, *, primary: bool = False) -> QPushButton:
        button = QPushButton(text)
        if primary:
            button.setObjectName("primary")
        if callback is not None:
            button.clicked.connect(callback)
        self._layout.addWidget(button)
        return button

    def finish(self) -> None:
        self._layout.addStretch()
        self._layout.addWidget(self.status, 1)


class EmptyState(QFrame):
    """Shared empty state panel for quiet, actionable blank states."""
    def __init__(self, title: str, copy: str, action_text: str = "", action=None):
        super().__init__()
        self.setObjectName("empty-state")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("empty-state-title")
        title_lbl.setWordWrap(True)
        layout.addWidget(title_lbl)

        copy_lbl = QLabel(copy)
        copy_lbl.setObjectName("empty-state-copy")
        copy_lbl.setWordWrap(True)
        layout.addWidget(copy_lbl)

        if action_text and action is not None:
            row = QHBoxLayout()
            row.setContentsMargins(0, 4, 0, 0)
            button = QPushButton(action_text)
            button.setObjectName("primary")
            button.clicked.connect(action)
            row.addWidget(button)
            row.addStretch()
            layout.addLayout(row)


class CommandResultPanel(QFrame):
    """Shared command feedback panel with copyable details."""
    def __init__(self, idle_text: str = ""):
        super().__init__()
        self.setObjectName("command-result-panel")
        self._details_text = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.status = StatusBadge(idle_text, "idle")
        layout.addWidget(self.status)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self._details_btn = QPushButton("Show details")
        self._details_btn.setCheckable(True)
        self._details_btn.toggled.connect(self._toggle_details)
        self._details_btn.hide()
        row.addWidget(self._details_btn)

        self._copy_btn = QPushButton("Copy details")
        self._copy_btn.clicked.connect(self._copy_details)
        self._copy_btn.hide()
        row.addWidget(self._copy_btn)
        row.addStretch()
        layout.addLayout(row)

        self._details = QTextEdit()
        self._details.document().setMaximumBlockCount(5000)
        self._details.setReadOnly(True)
        self._details.setMaximumHeight(120)
        self._details.hide()
        layout.addWidget(self._details)

    def set_result(self, state: str, text: str, details: str = "") -> None:
        self.status.set_state(state, text)
        self._details_text = details.strip()
        self._details.setPlainText(self._details_text)
        has_details = bool(self._details_text)
        self._details_btn.setVisible(has_details)
        self._copy_btn.setVisible(has_details)
        if not has_details:
            self._details.hide()
            self._details_btn.setChecked(False)
        self._copy_btn.setText("Copy details")
        self.show()

    def set_running(self, text: str, details: str = "") -> None:
        self.set_result("running", text, details)

    def _toggle_details(self, expanded: bool) -> None:
        self._details_btn.setText("Hide details" if expanded else "Show details")
        self._details.setVisible(expanded)

    def _copy_details(self) -> None:
        QApplication.clipboard().setText(self._details_text)
        self._copy_btn.setText("Copied")
        single_shot(self, 1200, lambda: self._copy_btn.setText("Copy details"))


def _make_flow_step(number: int, title: str, copy: str) -> QFrame:
    step = QFrame()
    step.setObjectName("flow-step")
    layout = QHBoxLayout(step)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(12)

    num = QLabel(str(number))
    num.setObjectName("flow-step-num")
    num.setFixedSize(22, 22)
    num.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(num, 0, Qt.AlignmentFlag.AlignTop)

    text_col = QVBoxLayout()
    text_col.setSpacing(2)
    title_lbl = QLabel(title)
    title_lbl.setObjectName("flow-step-title")
    title_lbl.setWordWrap(True)
    text_col.addWidget(title_lbl)
    copy_lbl = QLabel(copy)
    copy_lbl.setObjectName("flow-step-copy")
    copy_lbl.setWordWrap(True)
    text_col.addWidget(copy_lbl)
    layout.addLayout(text_col, 1)
    return step


class AppImageDropCard(QFrame):
    _IMAGE_RE = re.compile(r"\.(png|svg|svgz|jpg|jpeg|webp|ico|xpm)$", re.I)

    def __init__(self, on_appimage_drop, on_icon_drop=None):
        super().__init__()
        self._on_appimage_drop = on_appimage_drop
        self._on_icon_drop = on_icon_drop
        self.setObjectName("drop-card")
        self.setAcceptDrops(True)

    @classmethod
    def _is_icon_path(cls, path: str) -> bool:
        return bool(path and cls._IMAGE_RE.search(path))

    def _dropped_path(self, event) -> tuple[str, str]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return "", ""
        for url in mime.urls():
            path = url.toLocalFile()
            if path and re.search(r"\.[Aa]pp[Ii]mage$", path):
                return "appimage", path
            if self._on_icon_drop and self._is_icon_path(path):
                return "icon", path
        return "", ""

    def dragEnterEvent(self, event):  # noqa: N802
        kind, _ = self._dropped_path(event)
        if kind:
            self.setObjectName("drop-card-active")
            restyle(self)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):  # noqa: N802
        kind, _ = self._dropped_path(event)
        if kind:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):  # noqa: N802
        self.setObjectName("drop-card")
        restyle(self)
        event.accept()

    def dropEvent(self, event):  # noqa: N802
        self.setObjectName("drop-card")
        restyle(self)
        kind, path = self._dropped_path(event)
        if not kind or not path:
            event.ignore()
            return
        event.acceptProposedAction()
        if kind == "icon":
            self._on_icon_drop(path)
        else:
            self._on_appimage_drop(path)

def _set_log_panel(toggle: QPushButton, log: QTextEdit, expanded: bool):
    toggle.blockSignals(True)
    toggle.setChecked(expanded)
    toggle.blockSignals(False)
    toggle.setText("Hide details" if expanded else "Show details")
    log.setVisible(expanded)


class CollapsibleLogPanel(QWidget):
    """Shared "Show details" toggle + read-only log, for pages that stream
    live worker/command output (kernel switch, branch rebase, driver and
    tool installs, ...). CommandResultPanel doesn't fit these — it renders
    one result after a command finishes, not a live-appended stream — but
    17 pages had each hand-rolled this exact toggle+QTextEdit pairing
    independently, and three of those copies had already drifted to omit
    the block-count cap, letting a chatty install grow the widget's
    document unbounded.

    Height is per-page configurable (existing call sites use everything
    from a 100px max height to a 200px min height) via min_height/max_height
    — pass whichever the page previously set, to keep layouts unchanged.
    """

    def __init__(self, *, min_height: int | None = None, max_height: int | None = None):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.toggle = QPushButton("Show details")
        self.toggle.setCheckable(True)
        self.toggle.clicked.connect(self._on_toggle)
        self.toggle.hide()
        layout.addWidget(self.toggle)

        self.log = QTextEdit()
        self.log.document().setMaximumBlockCount(5000)
        self.log.setReadOnly(True)
        if min_height is not None:
            self.log.setMinimumHeight(min_height)
        if max_height is not None:
            self.log.setMaximumHeight(max_height)
        self.log.hide()
        layout.addWidget(self.log)

    def _on_toggle(self, checked: bool) -> None:
        _set_log_panel(self.toggle, self.log, checked)

    def set_expanded(self, expanded: bool) -> None:
        """Force the log open or collapsed — e.g. auto-expand on failure so
        the user doesn't have to click "Show details" to see why."""
        _set_log_panel(self.toggle, self.log, expanded)

    def reset(self, first_line: str = "") -> None:
        """Clear the log and collapse it, ready for a fresh run. Reveals
        the toggle (hidden until the first run) when first_line is given."""
        self.log.clear()
        _set_log_panel(self.toggle, self.log, False)
        if first_line:
            self.log.append(first_line)
            self.toggle.show()

    def append(self, text: str) -> None:
        self.log.append(text)
        self.log.ensureCursorVisible()


# ── Hardware card widget ───────────────────────────────────────────────────────
class HardwareCard(QFrame):
    _CARD_NAME: ClassVar[dict[str, str]] = {
        "ok":   "hw-card-ok",
        "warn": "hw-card-warn",
        "err":  "hw-card-err",
        "dim":  "hw-card-dim",
    }
    _BADGE_STYLE: ClassVar[dict[str, tuple[str, str]]] = {
        "ok":   ("status-ok",   "OK"),
        "warn": ("status-warn", "Warning"),
        "err":  ("status-err",  "Issue"),
        "dim":  ("status-dim",  "Info"),
    }

    def __init__(self, probe: HardwareProbe):
        super().__init__()
        self.setObjectName("hw-card-dim")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expanded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(0)

        # Always-visible summary row: title + badge
        top = QHBoxLayout()
        top.setSpacing(10)
        self._title = QLabel()
        self._title.setObjectName("card-title")
        top.addWidget(self._title)
        top.addStretch()
        self._badge = QLabel()
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self._badge)
        layout.addLayout(top)

        layout.addSpacing(6)

        # Always-visible one-line summary
        self._summary = QLabel()
        self._summary.setWordWrap(False)
        self._summary.setObjectName("card-copy")
        layout.addWidget(self._summary)

        # Detail section — hidden until user clicks
        self._detail_block = QWidget()
        detail_layout = QVBoxLayout(self._detail_block)
        detail_layout.setContentsMargins(0, 10, 0, 0)
        detail_layout.setSpacing(8)

        self._details = QLabel()
        self._details.setObjectName("card-copy")
        self._details.setWordWrap(True)
        self._details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail_layout.addWidget(self._details)

        self._action = QLabel()
        self._action.setWordWrap(True)
        self._action.setObjectName("card-action")
        detail_layout.addWidget(self._action)

        self._action_btn = QPushButton()
        self._action_btn.setObjectName("primary")
        self._action_btn.hide()
        detail_layout.addWidget(self._action_btn)

        self._detail_block.hide()
        layout.addWidget(self._detail_block)

        self.update_probe(probe)

    def mousePressEvent(self, event):
        self._expanded = not self._expanded
        self._detail_block.setVisible(self._expanded)
        super().mousePressEvent(event)

    def expand(self):
        if not self._expanded:
            self._expanded = True
            self._detail_block.setVisible(True)

    def update_probe(self, probe: HardwareProbe):
        self._title.setText(probe.title)
        self._summary.setText(probe.summary)
        self._details.setText(probe.details)

        badge_name, badge_text = self._BADGE_STYLE.get(
            probe.status, self._BADGE_STYLE["dim"]
        )
        self._badge.setText(badge_text)
        self._badge.setObjectName(badge_name)
        restyle(self._badge)

        card_name = self._CARD_NAME.get(probe.status, "hw-card-dim")
        self.setObjectName(card_name)
        restyle(self)

        if probe.action:
            self._action.setText(probe.action)
            self._action.show()
        else:
            self._action.hide()

    def set_action_fn(self, label: str, fn) -> None:
        self._action.hide()
        self._action_btn.setText(label)
        try:
            self._action_btn.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._action_btn.clicked.connect(fn)
        self._action_btn.show()


# ── Stat tile widget ───────────────────────────────────────────────────────────
class StatTile(QFrame):
    def __init__(self, label: str, value: str, value_style: str = "stat-value"):
        super().__init__()
        self.setObjectName("stat-tile")
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        self._label = QLabel(label.upper())
        self._label.setObjectName("stat-label")
        layout.addWidget(self._label)

        self._value = QLabel(value)
        self._value.setObjectName(value_style)
        self._value.setWordWrap(True)
        layout.addWidget(self._value)

    def set_value(self, value: str, style: str = "stat-value"):
        self._value.setText(value)
        self._value.setObjectName(style)
        restyle(self._value)


# ── Page base ─────────────────────────────────────────────────────────────────
class _NoAutoScrollArea(QScrollArea):
    """QScrollArea that does not jump to newly visible/focused child widgets."""
    def ensureWidgetVisible(self, widget, xmargin=50, ymargin=50):
        pass  # suppress automatic scroll-to-child on show/focus


class Page(QWidget):
    """Base page — provides a scrollable content area with consistent padding.

    Subclasses can call _page_header(eyebrow, title, subtitle) to render a
    distinct header band before the scroll area, matching the wizard style.
    """
    def __init__(self):
        super().__init__()
        self.setObjectName("content-area")

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        scroll = _NoAutoScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._outer.addWidget(scroll)

        container = QWidget()
        container.setObjectName("content-area")
        scroll.setWidget(container)

        self._layout = QVBoxLayout(container)
        # Right padding accounts for the 8 px vertical scrollbar overlap
        self._layout.setContentsMargins(48, 34, 56, 42)
        self._layout.setSpacing(18)

    def _page_header(self, eyebrow: str, title: str, subtitle: str = "") -> None:
        """Insert a styled header band at the top of the page (above scroll)."""
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

        # Insert header before the scroll area
        self._outer.insertWidget(0, hdr)
        self._outer.insertWidget(1, _divider())

    def _add(self, widget: QWidget) -> QWidget:
        self._layout.addWidget(widget)
        return widget

    def _add_layout(self, layout) -> None:
        self._layout.addLayout(layout)

    def _stretch(self):
        self._layout.addStretch()

    def _heading(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("heading")
        self._add(lbl)
        return lbl

    def _subheading(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("subheading")
        lbl.setWordWrap(True)
        self._add(lbl)
        return lbl

    def _divider(self):
        self._add(_divider())
