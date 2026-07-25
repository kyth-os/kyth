"""Header QSS styles."""
from ..ui_tokens import (
    KYTH_BLUE_LIGHT, KYTH_GROUND, KYTH_HAIRLINE, KYTH_TEXT, KYTH_TEXT_MUTED,
)

HEADER_QSS = f"""
/* ── Page header band ────────────────────────────────────────────────────── */
QWidget#page-header {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {KYTH_HAIRLINE}, stop:1 {KYTH_GROUND});
    border-bottom: 1px solid {KYTH_HAIRLINE};
}}

QLabel#eyebrow {{
    color: {KYTH_BLUE_LIGHT};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 0;
}}

QLabel#heading {{
    font-size: 30px;
    font-weight: 700;
    color: {KYTH_TEXT};
}}

QLabel#subheading {{
    font-size: 13px;
    color: {KYTH_TEXT_MUTED};
}}

QLabel#section-heading {{
    font-size: 16px;
    font-weight: 600;
    color: {KYTH_TEXT};
}}
"""
