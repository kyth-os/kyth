"""Mission bar — subtle status strip, not a second header.

SteamOS shows a thin persistent status line (time, battery, network) above the
library. Windows Settings has no equivalent, so this is Kyth's own: a
low-contrast strip that reads as chrome, not content. Slightly translucent
surface + smaller pills so it doesn't compete with the topbar.
"""
from ..ui_tokens import KYTH_BLUE, KYTH_HAIRLINE, KYTH_SURFACE, KYTH_TEXT_FAINT, KYTH_TEXT_MUTED, KYTH_WARN

MISSION_QSS = f"""
/* ── Mission bar ───────────────────────────────────────────────────────── */
QWidget#mission-bar {{
    background: {KYTH_SURFACE};
    border-bottom: 1px solid {KYTH_HAIRLINE};
}}

QLabel#mission-kicker {{
    color: {KYTH_TEXT_FAINT};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.7px;
}}

QLabel#mission-pill-dim {{
    background: transparent;
    color: {KYTH_TEXT_MUTED};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 999px;
    padding: 2px 9px;
    font-size: 11px;
    font-weight: 600;
}}

QLabel#mission-pill-warn {{
    background: rgba(255, 180, 0, 0.12);
    color: {KYTH_WARN};
    border: 1px solid rgba(255, 180, 0, 0.30);
    border-radius: 999px;
    padding: 2px 9px;
    font-size: 11px;
    font-weight: 700;
}}

QPushButton#mission-pill-warn {{
    background: rgba(255, 180, 0, 0.12);
    color: {KYTH_WARN};
    border: 1px solid rgba(255, 180, 0, 0.30);
    border-radius: 999px;
    padding: 2px 9px;
    font-size: 11px;
    font-weight: 700;
    text-align: center;
}}
QPushButton#mission-pill-warn:hover {{
    background: rgba(255, 180, 0, 0.18);
    border-color: rgba(255, 180, 0, 0.45);
}}

QLabel#mission-sep {{
    color: {KYTH_HAIRLINE};
    font-size: 12px;
}}
"""
