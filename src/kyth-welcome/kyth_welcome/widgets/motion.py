"""Lightweight fade-in for page/panel transitions.

Qt Style Sheets have no `transition` property, so every hover/press/active
state change driven by theme_base's QSS snaps instantly — MOTION_FAST /
MOTION_NORMAL (ui_tokens.py) were defined as tokens for this but never
actually wired up anywhere. fade_in() is the first user: a plain
QGraphicsOpacityEffect + QPropertyAnimation, mirroring the installer's own
page-transition fade, that self-detaches once done so a widget doesn't carry
effect-compositing overhead after the transition finishes.
"""
from __future__ import annotations

from ..qt import QEasingCurve, QGraphicsOpacityEffect, QPropertyAnimation, QWidget
from ..ui_tokens import MOTION_NORMAL


def fade_in(widget: QWidget, duration: int = MOTION_NORMAL) -> None:
    """Fade `widget` in from transparent to opaque over `duration` ms.

    Mirrors ``single_shot``'s ownership trick (qt.py): the QPropertyAnimation
    is parented to `widget` itself so Qt keeps it alive for the duration
    without a Python-side reference table to maintain.
    """
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _drop_effect():
        # Leaving the opacity effect attached forces Qt to composite the
        # widget via an offscreen pixmap on every repaint even once it's
        # fully opaque again — detach it once the fade completes.
        if widget.graphicsEffect() is effect:
            widget.setGraphicsEffect(None)

    anim.finished.connect(_drop_effect)
    anim.start()
