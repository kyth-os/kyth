"""Sidebar — SteamOS library rail + Windows Settings grouping.

The rail now reads as an inset panel (ground but with its own hairline top
highlight) so it lifts off the main canvas. Active item uses a pill + blue
accent stripe + subtle glow, matching Steam's focus treatment without copying
its orange. Section labels stay muted upper-case but with more air.
"""
from ..ui_tokens import KYTH_BLUE, KYTH_BLUE_GLOW, KYTH_HAIRLINE, KYTH_SURFACE, KYTH_SURFACE_RAISED, KYTH_TEXT, KYTH_TEXT_FAINT, KYTH_TEXT_MUTED

SIDEBAR_QSS = f"""
/* ── Sidebar — control-center rail ─────────────────────────────────────── */
QWidget#sidebar {{
    background: #0a0e14;
    border-right: 1px solid {KYTH_HAIRLINE};
}}

QScrollArea#sidebar-scroll {{
    background: transparent;
    border: none;
}}

QWidget#sidebar-scroll-content {{
    background: transparent;
}}

QWidget#sidebar-header {{
    background: transparent;
    border-bottom: 1px solid {KYTH_HAIRLINE};
}}

QLabel#sidebar-logo {{
    font-size: 18px;
    font-weight: 800;
    letter-spacing: -0.3px;
    color: {KYTH_TEXT};
    padding: 0;
}}

QLabel#sidebar-ver {{
    font-size: 11px;
    color: {KYTH_TEXT_FAINT};
    font-weight: 600;
    letter-spacing: 0.4px;
    padding: 0;
}}

QLabel#nav-section {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.9px;
    color: {KYTH_TEXT_FAINT};
    padding: 0 0 3px 0;
}}

QPushButton#nav-item,
QPushButton#nav-item-active {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    margin: 1px 8px;
    padding: 7px 10px;
    text-align: left;
    font-size: 13px;
}}

QPushButton#nav-item {{
    color: {KYTH_TEXT_MUTED};
    font-weight: 500;
}}

QPushButton#nav-item:hover {{
    background: {KYTH_SURFACE};
    color: {KYTH_TEXT};
    border-color: {KYTH_HAIRLINE};
}}

QPushButton#nav-item:pressed {{
    background: {KYTH_SURFACE_RAISED};
}}

QPushButton#nav-item:focus {{
    border: 1px solid {KYTH_BLUE};
}}

QPushButton#nav-item-active {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {KYTH_BLUE_GLOW}, stop:0.35 {KYTH_SURFACE_RAISED}, stop:1 {KYTH_SURFACE});
    color: {KYTH_TEXT};
    border: 1px solid {KYTH_HAIRLINE};
    border-left: 3px solid {KYTH_BLUE};
    padding: 7px 10px 7px 7px;
    font-weight: 700;
}}
"""
