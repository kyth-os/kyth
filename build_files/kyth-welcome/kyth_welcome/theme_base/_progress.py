"""Progress QSS styles."""
from ..ui_tokens import KYTH_BLUE, KYTH_SURFACE_RAISED

PROGRESS_QSS = f"""
/* ── Progress bar ────────────────────────────────────────────────────────── */
QProgressBar {{
    background: {KYTH_SURFACE_RAISED};
    border: none;
    border-radius: 3px;
    max-height: 5px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background: {KYTH_BLUE};
    border-radius: 3px;
}}
"""
