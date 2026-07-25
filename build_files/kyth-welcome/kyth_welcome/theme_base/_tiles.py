"""Tiles QSS styles."""
from ..ui_tokens import KYTH_TEXT, KYTH_TEXT_FAINT, STATUS_OK, STATUS_WARN

TILES_QSS = f"""
/* ── Stat tiles ──────────────────────────────────────────────────────────── */
QLabel#stat-label {{
    font-size: 11px;
    font-weight: 600;
    color: {KYTH_TEXT_FAINT};
}}

QLabel#stat-value {{
    font-size: 16px;
    font-weight: 600;
    color: {KYTH_TEXT};
}}

QLabel#stat-value-ok {{
    font-size: 16px;
    font-weight: 600;
    color: {STATUS_OK};
}}

QLabel#stat-value-warn {{
    font-size: 16px;
    font-weight: 600;
    color: {STATUS_WARN};
}}
"""
