"""Top command bar — SteamOS header meets Windows Settings command bar.

Surface is now inset from ground, with a crisp hairline bottom and a
hairline-top highlight to suggest elevation. Search becomes a pill-style
Windows Settings search with a blue focus ring and subtle inner depth.
Breadcrumb and nav arrows use rounded 8px and raised hover so the header
doesn't read as flat text on flat surface.
"""
from ..ui_tokens import KYTH_BLUE, KYTH_BLUE_LIGHT, KYTH_HAIRLINE, KYTH_HAIRLINE_LIGHT, KYTH_SURFACE, KYTH_SURFACE_RAISED, KYTH_SURFACE_OVERLAY, KYTH_TEXT, KYTH_TEXT_FAINT, KYTH_TEXT_MUTED

TOPBAR_QSS = f"""
/* ── Top command bar ─────────────────────────────────────────────────────── */
QWidget#topbar {{
    background: {KYTH_SURFACE};
    border-bottom: 1px solid {KYTH_HAIRLINE};
}}

QPushButton#topbar-nav {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 8px;
    padding: 4px 0;
    font-size: 15px;
    font-weight: 500;
}}

QPushButton#topbar-nav:hover {{
    background: {KYTH_SURFACE_OVERLAY};
    border-color: {KYTH_BLUE};
    color: {KYTH_BLUE_LIGHT};
}}

QPushButton#topbar-nav:pressed {{
    background: {KYTH_SURFACE};
}}

QPushButton#topbar-nav:disabled {{
    color: {KYTH_TEXT_FAINT};
    background: transparent;
    border-color: transparent;
}}

QPushButton#breadcrumb-link {{
    background: transparent;
    color: {KYTH_TEXT};
    border: none;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 13px;
    font-weight: 700;
    text-align: left;
}}

QPushButton#breadcrumb-link:hover {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_BLUE_LIGHT};
}}

QLabel#breadcrumb {{
    color: {KYTH_TEXT_FAINT};
    font-size: 13px;
}}

QLineEdit#search-box {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 10px;
    padding: 7px 14px;
    selection-background-color: {KYTH_BLUE};
    selection-color: #ffffff;
}}

QLineEdit#search-box:focus {{
    background: {KYTH_SURFACE_OVERLAY};
    border: 1px solid {KYTH_BLUE};
}}

QLineEdit#search-box:hover {{
    border-color: {KYTH_HAIRLINE_LIGHT};
}}

QFrame#search-results-panel {{
    background: {KYTH_SURFACE_RAISED};
    border-bottom: 1px solid {KYTH_HAIRLINE_LIGHT};
    border-left: 1px solid {KYTH_HAIRLINE_LIGHT};
    border-right: 1px solid {KYTH_HAIRLINE_LIGHT};
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
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
    background: {KYTH_SURFACE};
    color: {KYTH_TEXT_MUTED};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 10px;
    padding: 9px 12px;
    text-align: left;
    font-size: 12px;
}}

QPushButton#search-result:hover {{
    background: {KYTH_SURFACE_OVERLAY};
    color: {KYTH_TEXT};
    border-color: {KYTH_BLUE};
}}

QPushButton#search-result:pressed {{
    background: {KYTH_SURFACE};
}}
"""
