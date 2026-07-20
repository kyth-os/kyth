"""Switcher QSS styles."""
from ..ui_tokens import (
    KYTH_BLUE_LIGHT, KYTH_HAIRLINE, KYTH_SURFACE, KYTH_SURFACE_RAISED,
    KYTH_TEXT, KYTH_TEXT_FAINT, KYTH_TEXT_MUTED,
)

SWITCHER_QSS = f"""
/* ── Gaming section switcher ─────────────────────────────────────────────── */
QFrame#gaming-section-switcher {{
    background: transparent;
    border: none;
}}

QWidget#gaming-section-row {{
    background: transparent;
}}

QPushButton#gaming-section,
QPushButton#gaming-section-active {{
    border-radius: 5px;
    padding: 7px 14px;
    font-weight: 600;
}}

QPushButton#gaming-section {{
    background: {KYTH_SURFACE};
    color: {KYTH_TEXT_MUTED};
    border: 1px solid {KYTH_HAIRLINE};
}}

QPushButton#gaming-section:hover {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT};
    border-color: {KYTH_TEXT_FAINT};
}}

QPushButton#gaming-section-active {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT};
    border: 1px solid {KYTH_BLUE_LIGHT};
}}
"""
