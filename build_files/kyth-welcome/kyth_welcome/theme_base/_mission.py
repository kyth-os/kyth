"""Mission bar QSS — the always-visible system strip under topbar.

Single surface + hairline, no glow, no gradient. Pills reuse status-badge-*.
"""
from ..ui_tokens import KYTH_HAIRLINE, KYTH_SURFACE, KYTH_TEXT, KYTH_TEXT_FAINT, KYTH_TEXT_MUTED

MISSION_QSS = f"""
/* ── Mission bar ───────────────────────────────────────────────────────── */
QWidget#mission-bar {{
    background: {KYTH_SURFACE};
    border-bottom: 1px solid {KYTH_HAIRLINE};
}}

QLabel#mission-kicker {{
    color: {KYTH_TEXT_FAINT};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
}}

QLabel#mission-pill-dim {{
    background: {KYTH_SURFACE};
    color: {KYTH_TEXT_MUTED};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}}

QLabel#mission-sep {{
    color: {KYTH_HAIRLINE};
    font-size: 12px;
}}
"""
