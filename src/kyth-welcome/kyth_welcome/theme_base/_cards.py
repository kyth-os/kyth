"""Cards — layered panels with Steam-like hover elevation."""
from ..ui_tokens import KYTH_BLUE, KYTH_BLUE_LIGHT, KYTH_HAIRLINE, KYTH_HAIRLINE_LIGHT, KYTH_RADIUS, KYTH_RADIUS_SM, KYTH_SURFACE, KYTH_SURFACE_RAISED, KYTH_TEXT, KYTH_TEXT_FAINT, KYTH_TEXT_MUTED, STATUS_ERROR, STATUS_OK, STATUS_WARN

CARDS_QSS = f"""
/* ── Cards — control-center panels ─────────────────────────────────────── */
QFrame#card,
QFrame#home-recommend-card,
QFrame#home-action-card,
QFrame#stat-tile,
QFrame#summary-tile,
QFrame#home-action,
QFrame#home-section-header,
QFrame#starter-pack,
QFrame#ready-panel,
QFrame#store-app-card,
QFrame#store-category-card,
QFrame#card-accent-ok,
QFrame#card-accent-warn,
QFrame#card-accent-err,
QFrame#card-accent-dim,
QFrame#hw-card-dim {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS}px;
}}

QFrame#card,
QFrame#home-section-header {{
    padding: 0;
}}

QFrame#card:hover,
QFrame#home-recommend-card:hover,
QFrame#home-action-card:hover,
QFrame#stat-tile:hover,
QFrame#summary-tile:hover,
QFrame#home-action:hover,
QFrame#store-app-card:hover,
QFrame#store-category-card:hover {{
    background: {KYTH_SURFACE_RAISED};
    border-color: {KYTH_HAIRLINE_LIGHT};
}}

QFrame#card-accent-ok {{
    border-left: 3px solid {STATUS_OK};
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(16, 185, 129, 0.08), stop:1 {KYTH_SURFACE});
}}

QFrame#card-accent-warn {{
    border-left: 3px solid {STATUS_WARN};
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(245, 158, 11, 0.08), stop:1 {KYTH_SURFACE});
}}

QFrame#card-accent-err {{
    border-left: 3px solid {STATUS_ERROR};
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(247, 118, 142, 0.08), stop:1 {KYTH_SURFACE});
}}

QFrame#card-accent-dim,
QFrame#hw-card-dim {{
    border-left: 3px solid {KYTH_TEXT_FAINT};
}}

QLabel#card-title {{
    font-size: 15px;
    font-weight: 700;
    letter-spacing: -0.2px;
    color: {KYTH_TEXT};
}}

QLabel#card-title-warn {{
    font-size: 15px;
    font-weight: 700;
    letter-spacing: -0.2px;
    color: {STATUS_WARN};
}}

QLabel#card-title-err {{
    font-size: 15px;
    font-weight: 700;
    letter-spacing: -0.2px;
    color: {STATUS_ERROR};
}}

QLabel#card-subtitle {{
    font-size: 13px;
    font-weight: 600;
    color: {KYTH_TEXT};
}}

QLabel#card-summary,
QLabel#subheading {{
    color: {KYTH_TEXT_MUTED};
}}

QLabel#card-action {{
    color: {KYTH_BLUE_LIGHT};
}}

QLabel#card-copy {{
    color: {KYTH_TEXT_MUTED};
    line-height: 1.4;
}}

QLabel#section-title {{
    font-size: 15px;
    font-weight: 700;
    letter-spacing: -0.2px;
    color: {KYTH_TEXT};
}}
QLabel#section-subtitle {{
    font-size: 12px;
    color: {KYTH_TEXT_MUTED};
}}
QFrame#section-header {{
    background: transparent;
    border: none;
}}
QLabel#status-badge-ok,
QLabel#status-badge-warn,
QLabel#status-badge-err,
QLabel#status-badge-dim {{
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#status-badge-ok {{ background: {STATUS_OK}; color: #06120e; }}
QLabel#status-badge-warn {{ background: {STATUS_WARN}; color: #1a1200; }}
QLabel#status-badge-err {{ background: {STATUS_ERROR}; color: #1a0a0d; }}
QLabel#status-badge-dim {{ background: {KYTH_SURFACE_RAISED}; color: {KYTH_TEXT_FAINT}; border: 1px solid {KYTH_HAIRLINE}; }}

QFrame#home-recommend-card {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {KYTH_SURFACE}, stop:1 {KYTH_SURFACE_RAISED});
    border: 1px solid {KYTH_HAIRLINE};
    border-left: 3px solid {KYTH_BLUE};
    border-radius: {KYTH_RADIUS}px;
}}

QLabel#home-kicker {{
    color: {KYTH_BLUE_LIGHT};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.9px;
}}

QFrame#home-section {{
    background: transparent;
    border: none;
}}

QLabel#home-section-title {{
    color: {KYTH_TEXT};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: -0.2px;
}}

QLabel#home-section-copy {{
    color: {KYTH_TEXT_MUTED};
    font-size: 12px;
}}

QLabel#home-action-icon {{
    font-size: 22px;
    font-weight: 600;
    color: {KYTH_BLUE_LIGHT};
}}

QLabel#home-action-title {{
    font-size: 15px;
    font-weight: 600;
    color: {KYTH_TEXT};
}}

QLabel#home-action-copy {{
    color: {KYTH_TEXT_MUTED};
}}

QLabel#home-next-title {{
    font-size: 24px;
    font-weight: 800;
    letter-spacing: -0.5px;
    color: {KYTH_TEXT};
}}

QLabel#home-next-copy {{
    color: {KYTH_TEXT_MUTED};
}}

QLabel#home-next-meta {{
    color: {KYTH_BLUE_LIGHT};
}}

QPushButton#starter-pack-header {{
    background: transparent;
    border: none;
    color: {KYTH_TEXT};
    text-align: left;
    font-size: 14px;
    font-weight: 600;
    padding: 0;
}}

QPushButton#starter-pack-header:hover {{
    color: {KYTH_BLUE_LIGHT};
}}

QLabel#starter-pack-meta {{
    color: {KYTH_BLUE_LIGHT};
    font-size: 11px;
    font-weight: 600;
}}

QWidget#starter-pack-details {{
    background: transparent;
}}

QFrame#store-hero {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {KYTH_SURFACE}, stop:1 {KYTH_SURFACE_RAISED});
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS}px;
}}

QLabel#store-hero-title {{
    font-size: 20px;
    font-weight: 700;
    letter-spacing: -0.3px;
    color: {KYTH_TEXT};
}}

QLabel#store-kicker {{
    color: {KYTH_BLUE_LIGHT};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.9px;
}}

QFrame#drop-card {{
    background: {KYTH_SURFACE};
    border: 1px dashed {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS}px;
}}

QFrame#drop-card-active {{
    background: {KYTH_SURFACE_RAISED};
    border: 2px dashed {KYTH_BLUE_LIGHT};
    border-radius: {KYTH_RADIUS}px;
}}

QLabel#drop-glyph {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_BLUE_LIGHT};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS_SM}px;
    font-size: 12px;
    font-weight: 600;
}}

QLabel#drop-title {{
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.2px;
    color: {KYTH_TEXT};
}}

/* ── Setting rows — name + description + trailing switch/badge ─────────── */
QFrame#setting-row {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {KYTH_HAIRLINE};
}}

QLabel#setting-row-title {{
    font-size: 13px;
    font-weight: 600;
    color: {KYTH_TEXT};
}}

QLabel#setting-row-subtitle {{
    font-size: 12px;
    color: {KYTH_TEXT_MUTED};
}}
"""
