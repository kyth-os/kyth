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

/* ── ProtonDB tier badges (bespoke medal-tier identity, not a status scale —
   platinum/gold/silver/bronze are deliberately distinct hues; borked/pending
   reuse the shared status-err/status-dim pills instead of duplicating them) */
QLabel#pdb-tier-platinum,
QLabel#pdb-tier-gold,
QLabel#pdb-tier-silver,
QLabel#pdb-tier-bronze {{
    border-radius: 3px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}}

QLabel#pdb-tier-platinum {{
    background: #102010;
    color: #7ee8a2;
    border: 1px solid #7ee8a2;
}}

QLabel#pdb-tier-gold {{
    background: #2b2410;
    color: #d4a843;
    border: 1px solid #d4a843;
}}

QLabel#pdb-tier-silver {{
    background: #181e2b;
    color: #8cadcf;
    border: 1px solid #8cadcf;
}}

QLabel#pdb-tier-bronze {{
    background: #2b1a10;
    color: #c47c4a;
    border: 1px solid #c47c4a;
}}
"""
