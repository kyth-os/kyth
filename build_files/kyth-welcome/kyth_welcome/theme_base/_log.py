"""Log — terminal style."""

from ..ui_tokens import KYTH_HAIRLINE, KYTH_SURFACE_RAISED

LOG_QSS = f"""
/* ── Text log ────────────────────────────────────────────────────────────── */
QTextEdit {{
    background: #12151c;
    color: #d8deeb;
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 8px;
    font-family: "Cascadia Code", "Noto Mono", "Consolas", monospace;
    font-size: 12px;
    padding: 12px 14px;
    selection-background-color: {KYTH_SURFACE_RAISED};
}}
"""
