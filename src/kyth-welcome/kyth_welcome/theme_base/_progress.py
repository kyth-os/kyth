"""Progress — slimmer, smoother, with overlay track."""

from ..ui_tokens import KYTH_BLUE, KYTH_SURFACE_OVERLAY

PROGRESS_QSS = f"""
/* ── Progress bar ────────────────────────────────────────────────────────── */
QProgressBar {{
    background: {KYTH_SURFACE_OVERLAY};
    border: none;
    border-radius: 4px;
    max-height: 6px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background: {KYTH_BLUE};
    border-radius: 4px;
}}
"""
