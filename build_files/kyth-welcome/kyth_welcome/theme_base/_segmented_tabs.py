"""Segmented-tab QSS — the one shared "sub-navigation within a page"
control. Was two identical rule sets: Home's workstation-mode switcher
(#genz-mode-btn/#genz-focus-row) and this one, added for App Store's
rebuilt tab bar (replacing its old #sw-tab underline row, which looked
enough like the sidebar's own nav to read as a second, competing
navigation system on the same page). Same visual language, so #genz-*
now just aliases these selectors instead of carrying a second copy of
the same rules — Gaming's hub tabs still use #genz-mode-btn directly and
can migrate to #segmented-tab whenever that page gets its own rebuild.
"""
from ..ui_tokens import KYTH_BLUE, KYTH_BLUE_LIGHT, KYTH_HAIRLINE, KYTH_SURFACE, KYTH_TEXT, KYTH_TEXT_MUTED

SEGMENTED_TABS_QSS = f"""
/* ── Segmented tabs (page-level sub-navigation) ─────────────────────────── */
QWidget#segmented-tab-row,
QWidget#genz-focus-row {{
    background-color: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 12px;
}}

QPushButton#segmented-tab,
QPushButton#genz-mode-btn {{
    background-color: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 8px;
    color: {KYTH_TEXT_MUTED};
    font-weight: 650;
    padding: 8px 16px;
}}

QPushButton#segmented-tab:hover,
QPushButton#genz-mode-btn:hover {{
    border-color: {KYTH_BLUE};
    color: {KYTH_TEXT};
}}

QPushButton#segmented-tab:checked,
QPushButton#genz-mode-btn:checked {{
    background-color: {KYTH_BLUE};
    border-color: {KYTH_BLUE_LIGHT};
    color: {KYTH_TEXT};
}}
"""
