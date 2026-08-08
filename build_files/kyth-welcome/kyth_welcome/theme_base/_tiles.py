"""Tiles — stat tiles for dashboards."""

from ..ui_tokens import KYTH_TEXT, KYTH_TEXT_MUTED, STATUS_OK, STATUS_WARN

TILES_QSS = f"""
/* ── Stat tiles ──────────────────────────────────────────────────────────── */
QLabel#stat-label {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.7px;
    color: {KYTH_TEXT_MUTED};
}}

QLabel#stat-value {{
    font-size: 16px;
    font-weight: 700;
    letter-spacing: -0.2px;
    color: {KYTH_TEXT};
}}

QLabel#stat-value-ok {{
    font-size: 16px;
    font-weight: 700;
    color: {STATUS_OK};
}}

QLabel#stat-value-warn {{
    font-size: 16px;
    font-weight: 700;
    color: {STATUS_WARN};
}}
"""
