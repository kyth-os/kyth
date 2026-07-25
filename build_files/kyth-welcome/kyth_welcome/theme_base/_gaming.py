"""Gaming QSS styles."""
from ..ui_tokens import (
    KYTH_HAIRLINE, KYTH_SURFACE, KYTH_TEXT_MUTED, STATUS_ERROR, STATUS_OK,
    STATUS_WARN,
)

GAMING_QSS = f"""
/* ── Gaming readiness panel ──────────────────────────────────────────────── */
QLabel#ready-score {{
    color: {STATUS_OK};
    font-size: 28px;
    font-weight: 700;
}}

QLabel#ready-score-warn {{
    color: {STATUS_WARN};
    font-size: 28px;
    font-weight: 700;
}}

QLabel#ready-score-err {{
    color: {STATUS_ERROR};
    font-size: 28px;
    font-weight: 700;
}}

QLabel#ready-row-ok,
QLabel#ready-row-warn,
QLabel#ready-row-err,
QLabel#ready-row-dim {{
    border-radius: 5px;
    padding: 8px 10px;
    font-weight: 600;
}}

QLabel#ready-row-ok {{
    background: rgba(16, 185, 129, 20);
    color: {STATUS_OK};
    border: 1px solid {STATUS_OK};
}}

QLabel#ready-row-warn {{
    background: rgba(245, 158, 11, 20);
    color: {STATUS_WARN};
    border: 1px solid {STATUS_WARN};
}}

QLabel#ready-row-err {{
    background: rgba(247, 118, 142, 20);
    color: {STATUS_ERROR};
    border: 1px solid {STATUS_ERROR};
}}

QLabel#ready-row-dim {{
    background: {KYTH_SURFACE};
    color: {KYTH_TEXT_MUTED};
    border: 1px solid {KYTH_HAIRLINE};
}}
"""
