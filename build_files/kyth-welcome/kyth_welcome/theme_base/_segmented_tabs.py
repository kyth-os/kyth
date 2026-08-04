"""Segmented-tab QSS — the one shared "sub-navigation within a page"
control. Same pill-checkable-button visual language Home's workstation-mode
switcher already established (there as #genz-mode-btn/#genz-focus-row);
named generically here since App Store adopts it too, replacing its old
#sw-tab underline row, which looked enough like the sidebar's own nav to
read as a second, competing navigation system on the same page.
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
    background-color: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 8px;
    color: {KYTH_TEXT_MUTED};
    font-weight: 650;
    padding: 8px 16px;
}}

QPushButton#segmented-tab:hover {{
    border-color: {KYTH_BLUE};
    color: {KYTH_TEXT};
}}

QPushButton#segmented-tab:checked {{
    background-color: {KYTH_BLUE};
    border-color: {KYTH_BLUE_LIGHT};
    color: {KYTH_TEXT};
}}
"""
