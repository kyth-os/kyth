"""Topbar QSS styles.

Kyth Theme: same token pass as _sidebar.py — the topbar now shares surface
and hairline tone with the wizard's footer bar (both KYTH_SURFACE on
KYTH_HAIRLINE), and the search focus state uses KYTH_BLUE to match the
wizard's accent language instead of a separate blue.
"""
from ..ui_tokens import (
    KYTH_BLUE, KYTH_HAIRLINE, KYTH_SURFACE, KYTH_SURFACE_RAISED, KYTH_TEXT,
    KYTH_TEXT_FAINT, KYTH_TEXT_MUTED,
)

TOPBAR_QSS = f"""
/* ── Top command bar ─────────────────────────────────────────────────────── */
QWidget#topbar {{
    background: {KYTH_SURFACE};
    border-bottom: 1px solid {KYTH_HAIRLINE};
}}

QPushButton#topbar-nav {{
    background: transparent;
    color: {KYTH_TEXT};
    border: none;
    border-radius: 5px;
    padding: 4px 0;
    font-size: 15px;
    font-weight: 400;
}}

QPushButton#topbar-nav:hover {{
    background: {KYTH_SURFACE_RAISED};
}}

QPushButton#topbar-nav:pressed {{
    background: {KYTH_HAIRLINE};
}}

QPushButton#topbar-nav:disabled {{
    color: {KYTH_TEXT_FAINT};
    background: transparent;
}}

QPushButton#breadcrumb-link {{
    background: transparent;
    color: {KYTH_TEXT};
    border: none;
    border-radius: 5px;
    padding: 4px 8px;
    font-size: 13px;
    font-weight: 700;
    text-align: left;
}}

QPushButton#breadcrumb-link:hover {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT};
}}

QLabel#breadcrumb {{
    color: {KYTH_TEXT_FAINT};
    font-size: 13px;
}}

QLineEdit#search-box {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT};
    border: 1px solid {KYTH_HAIRLINE};
    border-bottom: 1px solid {KYTH_TEXT_FAINT};
    border-radius: 5px;
    padding: 6px 12px;
}}

QLineEdit#search-box:focus {{
    background: {KYTH_SURFACE_RAISED};
    border-bottom: 2px solid {KYTH_BLUE};
}}

QFrame#search-results-panel {{
    background: {KYTH_SURFACE};
    border-bottom: 1px solid {KYTH_HAIRLINE};
}}

QLabel#search-results-title {{
    color: {KYTH_TEXT};
    font-size: 12px;
    font-weight: 700;
}}

QLabel#search-results-hint {{
    color: {KYTH_TEXT_FAINT};
    font-size: 11px;
}}

QPushButton#search-result {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT_MUTED};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 6px;
    padding: 8px 12px;
    text-align: left;
    font-size: 12px;
}}

QPushButton#search-result:hover {{
    background: {KYTH_HAIRLINE};
    color: {KYTH_TEXT};
    border-color: {KYTH_BLUE};
}}

QPushButton#search-result:pressed {{
    background: {KYTH_SURFACE};
}}
"""
