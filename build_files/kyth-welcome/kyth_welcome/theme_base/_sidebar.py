"""Sidebar QSS styles.

Kyth Theme: brought onto the same token set as the wizard's step rail
(ui_tokens.KYTH_*) so System Hub and first-boot setup read as one shell
instead of two separately-designed surfaces. Structure/selectors unchanged
from before — this is a color/token pass only, no windows.py changes needed.
"""
from ..ui_tokens import (
    KYTH_BLUE, KYTH_GROUND, KYTH_HAIRLINE, KYTH_SURFACE_RAISED, KYTH_TEXT,
    KYTH_TEXT_FAINT, KYTH_TEXT_MUTED,
)

SIDEBAR_QSS = f"""
/* ── Sidebar — Windows Settings density ────────────────────────────────── */
QWidget#sidebar {{
    background: {KYTH_GROUND};
    border-right: 1px solid {KYTH_HAIRLINE};
}}

QWidget#sidebar-header {{
    background: transparent;
    border-bottom: 1px solid {KYTH_HAIRLINE};
}}

QLabel#sidebar-logo {{
    font-size: 18px;
    font-weight: 800;
    letter-spacing: 0.2px;
    color: {KYTH_TEXT};
    padding: 0;
}}

QLabel#sidebar-ver {{
    font-size: 11px;
    color: {KYTH_TEXT_FAINT};
    font-weight: 600;
    padding: 0;
}}

QLabel#nav-section {{
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.7px;
    color: {KYTH_TEXT_FAINT};
    padding: 0 0 2px 0;
}}

QPushButton#nav-item,
QPushButton#nav-item-active {{
    background: transparent;
    border: none;
    border-radius: 6px;
    margin: 1px 8px;
    padding: 7px 10px;
    text-align: left;
    font-size: 13px;
}}

QPushButton#nav-item {{
    color: {KYTH_TEXT_MUTED};
    font-weight: 400;
}}

QPushButton#nav-item:hover {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT};
}}

QPushButton#nav-item:pressed {{
    background: {KYTH_HAIRLINE};
}}

QPushButton#nav-item:focus {{
    border: 1px solid {KYTH_BLUE};
}}

QPushButton#nav-item-active {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT};
    border-left: 2px solid {KYTH_BLUE};
    padding: 7px 10px 7px 8px;
    font-weight: 700;
}}
"""
