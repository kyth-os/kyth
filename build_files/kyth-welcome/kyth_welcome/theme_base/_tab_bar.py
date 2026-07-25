"""Tab Bar QSS styles."""
from ..ui_tokens import KYTH_BLUE_LIGHT, KYTH_SURFACE, KYTH_TEXT, KYTH_TEXT_MUTED

TAB_BAR_QSS = f"""
/* ── Software page tab bar ───────────────────────────────────────────────── */
QWidget#sw-tab-bar {{
    background: {KYTH_SURFACE};
}}

QPushButton#sw-tab,
QPushButton#sw-tab-active {{
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 10px 22px;
    font-size: 13px;
    min-width: 92px;
}}

QPushButton#sw-tab {{
    color: {KYTH_TEXT_MUTED};
    border-bottom: 2px solid transparent;
    font-weight: 400;
}}

QPushButton#sw-tab:hover {{
    background: {KYTH_SURFACE};
    color: {KYTH_TEXT};
}}

QPushButton#sw-tab-active {{
    color: {KYTH_TEXT};
    border-bottom: 2px solid {KYTH_BLUE_LIGHT};
    font-weight: 600;
}}
"""
