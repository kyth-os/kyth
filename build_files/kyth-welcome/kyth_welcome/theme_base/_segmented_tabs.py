"""Segmented-tab QSS — the one shared "sub-navigation within a page"
control. Used by Home's workstation-mode switcher, App Store's tab bar
(replacing its old #sw-tab underline row, which looked enough like the
sidebar's own nav to read as a second, competing navigation system on
the same page), and Gaming's hub tabs.
"""
from ..ui_tokens import KYTH_BLUE, KYTH_BLUE_LIGHT, KYTH_HAIRLINE, KYTH_SURFACE, KYTH_TEXT, KYTH_TEXT_MUTED

SEGMENTED_TABS_QSS = f"""
/* ── Segmented tabs (page-level sub-navigation) ─────────────────────────── */
QWidget#segmented-tab-row {{
    background-color: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 12px;
}}

QPushButton#segmented-tab {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    color: {KYTH_TEXT_MUTED};
    font-weight: 600;
    padding: 7px 14px;
}}

QPushButton#segmented-tab:hover {{
    background-color: {KYTH_SURFACE};
    border-color: {KYTH_HAIRLINE};
    color: {KYTH_TEXT};
}}

QPushButton#segmented-tab:checked {{
    background-color: {KYTH_BLUE};
    border-color: {KYTH_BLUE};
    color: #ffffff;
}}
"""
