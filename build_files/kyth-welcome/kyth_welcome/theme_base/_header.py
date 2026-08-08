"""Header QSS styles — page header band and heading/eyebrow typography."""
from ..ui_tokens import (
    KYTH_BLUE_LIGHT, KYTH_GROUND, KYTH_HAIRLINE, KYTH_TEXT, KYTH_TEXT_MUTED,
)

HEADER_QSS = f"""
/* ── Page header band ────────────────────────────────────────────────────── */
QWidget#page-header {{
    background: {KYTH_GROUND};
    border-bottom: 1px solid {KYTH_HAIRLINE};
}}

QLabel#page-eyebrow,
QLabel#eyebrow {{
    color: {KYTH_BLUE_LIGHT};
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.5px;
    padding: 0;
}}

QLabel#page-title,
QLabel#heading {{
    font-size: 24px;
    font-weight: 750;
    color: {KYTH_TEXT};
}}

QLabel#subheading,
QLabel#page-subtitle,
QLabel#wizard-desc {{
    font-size: 13px;
    color: {KYTH_TEXT_MUTED};
}}

QLabel#section-heading {{
    font-size: 16px;
    font-weight: 600;
    color: {KYTH_TEXT};
}}
"""
