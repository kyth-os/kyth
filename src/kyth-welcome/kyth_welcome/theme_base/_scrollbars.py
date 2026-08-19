"""Scrollbars — thinner, more Steam-like."""

from ..ui_tokens import KYTH_HAIRLINE, KYTH_TEXT_FAINT

SCROLLBARS_QSS = f"""
/* ── Scroll bars ─────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {KYTH_HAIRLINE};
    border-radius: 4px;
    min-height: 32px;
}}

QScrollBar::handle:vertical:hover {{
    background: {KYTH_TEXT_FAINT};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    background: transparent;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: {KYTH_HAIRLINE};
    border-radius: 4px;
    min-width: 32px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {KYTH_TEXT_FAINT};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
    background: transparent;
}}
"""
