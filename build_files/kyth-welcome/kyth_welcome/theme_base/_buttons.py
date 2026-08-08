"""Buttons QSS styles — one QPushButton base rule for the whole app.

#danger/#btn-secondary/#branch-* have no equivalent elsewhere and are
genuinely load-bearing.
"""
from ..ui_tokens import (
    KYTH_BLUE, KYTH_BLUE_DIM, KYTH_BLUE_LIGHT, KYTH_DANGER, KYTH_DANGER_LIGHT,
    KYTH_GROUND, KYTH_HAIRLINE, KYTH_RADIUS_SM, KYTH_SURFACE, KYTH_SURFACE_RAISED,
    KYTH_TEXT, KYTH_TEXT_FAINT, KYTH_TEXT_MUTED,
)

BUTTONS_QSS = f"""
/* ── Buttons ─────────────────────────────────────────────────────────────── */
QPushButton {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS_SM}px;
    padding: 7px 14px;
    font-size: 13px;
    font-weight: 600;
}}

QPushButton:hover {{
    background: {KYTH_HAIRLINE};
    color: {KYTH_TEXT};
    border-color: {KYTH_HAIRLINE};
}}

QPushButton:focus {{
    border: 1px solid {KYTH_BLUE};
}}

QPushButton:pressed {{
    background: {KYTH_SURFACE};
    color: {KYTH_TEXT_MUTED};
}}

QPushButton:disabled {{
    background: {KYTH_GROUND};
    color: {KYTH_TEXT_FAINT};
    border-color: {KYTH_HAIRLINE};
}}

QPushButton#primary,
QPushButton#btn-secondary,
QPushButton[primary="true"] {{
    background: {KYTH_BLUE};
    color: {KYTH_TEXT};
    border: 1px solid {KYTH_BLUE_LIGHT};
    font-weight: 600;
    padding: 8px 20px;
    letter-spacing: 0.3px;
}}

QPushButton#primary:hover,
QPushButton#btn-secondary:hover,
QPushButton[primary="true"]:hover {{
    background: {KYTH_BLUE_LIGHT};
    border-color: {KYTH_BLUE_LIGHT};
}}

QPushButton#primary:pressed,
QPushButton#btn-secondary:pressed,
QPushButton[primary="true"]:pressed {{
    background: {KYTH_BLUE_DIM};
}}

QPushButton#primary:disabled,
QPushButton#btn-secondary:disabled,
QPushButton[primary="true"]:disabled {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT_FAINT};
    border-color: {KYTH_HAIRLINE};
}}

QPushButton#danger {{
    background: {KYTH_DANGER};
    color: {KYTH_TEXT};
    border: 1px solid {KYTH_DANGER_LIGHT};
    font-weight: 600;
}}

QPushButton#danger:hover {{
    background: {KYTH_DANGER_LIGHT};
    border-color: #ff6b6b;
}}

QPushButton#danger:pressed {{
    background: #a72015;
}}

QPushButton#danger:disabled {{
    background: #2d1d1c;
    color: #6b5252;
    border-color: #3a2a29;
}}

QPushButton#branch-active {{
    background: {KYTH_BLUE};
    color: {KYTH_TEXT};
    font-weight: 600;
    border: 1px solid {KYTH_BLUE_LIGHT};
    border-radius: {KYTH_RADIUS_SM}px;
    padding: 9px 22px;
}}

QPushButton#branch-inactive {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT_MUTED};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS_SM}px;
    padding: 9px 22px;
}}

QPushButton#branch-inactive:hover {{
    background: {KYTH_HAIRLINE};
    color: {KYTH_TEXT};
    border-color: {KYTH_TEXT_FAINT};
}}
"""
