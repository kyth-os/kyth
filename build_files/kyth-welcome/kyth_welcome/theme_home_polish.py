"""Home page polish pass: transparent text, structure moved to panels.

Kyth Theme: tokenized alongside theme_hub_overlay.py.
"""
from .ui_tokens import (
    KYTH_BLUE_LIGHT, KYTH_GROUND, KYTH_HAIRLINE, KYTH_SURFACE,
    KYTH_SURFACE_RAISED, KYTH_TEXT, KYTH_TEXT_FAINT, KYTH_TEXT_MUTED,
    STATUS_OK, STATUS_WARN,
)

HOME_POLISH_QSS = f"""
/* Home polish pass: keep text transparent and move structure to panels. */
QWidget#page,
QScrollArea,
QScrollArea > QWidget,
QWidget#scroll-content {{
    background: {KYTH_GROUND};
}}

QLabel {{
    background: transparent;
}}

QFrame#card,
QFrame#card-accent-ok,
QFrame#card-accent-warn,
QFrame#stat-tile,
QFrame#summary-tile,
QFrame#home-action,
QFrame#home-section-header {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 8px;
}}

QFrame#card,
QFrame#home-section-header {{
    padding: 0;
}}


QFrame#stat-tile {{
    background: {KYTH_SURFACE};
    border-color: {KYTH_HAIRLINE};
}}

QFrame#stat-tile:hover,
QFrame#summary-tile:hover,
QFrame#home-action:hover {{
    background: {KYTH_SURFACE_RAISED};
    border-color: {KYTH_TEXT_FAINT};
}}

QLabel#home-section-title {{
    color: {KYTH_TEXT};
    font-size: 20px;
    font-weight: 700;
}}

QLabel#home-section-subtitle,
QLabel#card-copy,
QLabel#stat-label {{
    color: {KYTH_TEXT_MUTED};
}}

QLabel#home-kicker {{
    color: {KYTH_BLUE_LIGHT};
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
}}

QLabel#stat-value {{
    color: {KYTH_TEXT};
    font-size: 16px;
    font-weight: 600;
}}

QLabel#stat-value-ok {{
    color: {STATUS_OK};
}}

QLabel#stat-value-warn {{
    color: {STATUS_WARN};
}}

QPushButton#primary:hover {{
    background: {KYTH_BLUE_LIGHT};
}}
"""
