"""Modern pill-style toggle switch.

Every "on/off" setting in the Hub used a bare QCheckBox square (see
page_performance.py's auto-switch/AI-tuning checks) — functional, but flat
and easy to miss next to a page full of buttons and labels. ToggleSwitch is
a drop-in QCheckBox subclass (same setChecked()/isChecked()/toggled API, so
existing wiring — stateChanged.connect(...), blockSignals() while syncing
from a background probe — keeps working unchanged) that paints itself as an
animated pill switch instead of the default indicator square.
"""
from __future__ import annotations

from ..qt import (
    Property,
    QCheckBox,
    QColor,
    QEasingCurve,
    QPainter,
    QPropertyAnimation,
    QSize,
    Qt,
)
from ..ui_tokens import KYTH_BLUE, KYTH_SURFACE_RAISED, KYTH_TEXT, KYTH_TEXT_FAINT, MOTION_FAST

_TRACK_W = 40
_TRACK_H = 22
_THUMB_PAD = 3
_THUMB_D = _TRACK_H - (_THUMB_PAD * 2)


class ToggleSwitch(QCheckBox):
    """A single on/off pill switch with no label of its own — pair it with
    a QLabel (see widgets.cards._make_setting_row) for the setting's name."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setText("")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(_TRACK_W, _TRACK_H)
        self._offset = float(_THUMB_PAD)
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(MOTION_FAST)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setChecked(checked)

    def sizeHint(self) -> QSize:  # noqa: N802 -- Qt override signature
        return QSize(_TRACK_W, _TRACK_H)

    def _end_offset(self) -> float:
        return float(_TRACK_W - _THUMB_D - _THUMB_PAD) if self.isChecked() else float(_THUMB_PAD)

    def setChecked(self, checked: bool) -> None:  # noqa: N802 -- Qt override signature
        super().setChecked(checked)
        # Slide the thumb on every path that can flip the check state — a
        # user click, a programmatic setChecked(), and a
        # blockSignals()-guarded sync from a background probe (see
        # PerformancePage._apply_sched_daemon_state) all land here, so none
        # of them can leave the thumb painted on the wrong side because
        # `toggled` never fired.
        anim = getattr(self, "_anim", None)
        if anim is None:
            return
        anim.stop()
        anim.setStartValue(self._offset)
        anim.setEndValue(self._end_offset())
        anim.start()

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def paintEvent(self, event) -> None:  # noqa: N802 -- Qt override signature
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        painter.setBrush(QColor(KYTH_BLUE if self.isChecked() else KYTH_SURFACE_RAISED))
        painter.drawRoundedRect(0, 0, _TRACK_W, _TRACK_H, _TRACK_H / 2, _TRACK_H / 2)

        if not self.isChecked():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor(KYTH_TEXT_FAINT))
            painter.drawRoundedRect(0, 0, _TRACK_W - 1, _TRACK_H - 1, _TRACK_H / 2, _TRACK_H / 2)
            painter.setPen(Qt.PenStyle.NoPen)

        painter.setBrush(QColor(KYTH_TEXT))
        painter.drawEllipse(int(self._offset), _THUMB_PAD, _THUMB_D, _THUMB_D)
        painter.end()
