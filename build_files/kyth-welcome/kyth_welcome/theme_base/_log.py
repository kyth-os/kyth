"""Log QSS styles.

Background/text stay a neutral (non-blue-tinted) near-black — a deliberate
"terminal" treatment distinct from the rest of the app's chrome, kept as-is.
Only the structural border/selection are tokenized.
"""
from ..ui_tokens import KYTH_HAIRLINE, KYTH_SURFACE_RAISED

LOG_QSS = f"""
/* ── Text log ────────────────────────────────────────────────────────────── */
QTextEdit {{
    background: #1a1a1a;
    color: #d4d4d4;
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 5px;
    font-family: "Cascadia Code", "Noto Mono", "Consolas", monospace;
    font-size: 12px;
    padding: 12px 14px;
    selection-background-color: {KYTH_SURFACE_RAISED};
}}
"""
