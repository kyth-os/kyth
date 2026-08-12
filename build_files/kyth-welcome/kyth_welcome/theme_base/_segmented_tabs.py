"""Segmented tabs — Windows Settings pill switcher with Steam focus."""

from ..ui_tokens import KYTH_HAIRLINE, KYTH_PRIMARY_BG, KYTH_PRIMARY_BORDER, KYTH_PRIMARY_HOVER_BG, KYTH_PRIMARY_HOVER_BORDER, KYTH_SURFACE, KYTH_SURFACE_OVERLAY, KYTH_TEXT, KYTH_TEXT_MUTED

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
    background-color: {KYTH_SURFACE_OVERLAY};
    border-color: {KYTH_HAIRLINE};
    color: {KYTH_TEXT};
}}

QPushButton#segmented-tab:checked {{
    background-color: {KYTH_PRIMARY_BG};
    border-color: {KYTH_PRIMARY_BORDER};
    color: {KYTH_TEXT};
}}

QPushButton#segmented-tab:checked:hover {{
    background-color: {KYTH_PRIMARY_HOVER_BG};
    border-color: {KYTH_PRIMARY_HOVER_BORDER};
}}
"""
