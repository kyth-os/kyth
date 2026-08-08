"""Hero/HUD/category cards — Home dashboard.

Single-accent, layered surfaces: hero is surface+hairline (no purple
gradient), HUD tiles are surface→raised on hover, category cards get a
subtle hairline→blue on hover rather than permanent 5-hue stripes.
"""
from ..ui_tokens import (
    KYTH_BLUE, KYTH_BLUE_LIGHT, KYTH_HAIRLINE, KYTH_SURFACE,
    KYTH_SURFACE_RAISED, KYTH_TEXT, KYTH_TEXT_FAINT, KYTH_TEXT_MUTED,
    RADIUS_HERO, STATUS_ERROR, STATUS_OK, STATUS_WARN,
)

HERO_QSS = f"""
/* ── Hero / HUD / category cards ────────────────────────────────────────── */
QFrame#genz-hero {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {RADIUS_HERO}px;
}}

QLabel#genz-hero-title {{
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 0.3px;
    color: {KYTH_TEXT};
}}

QLabel#genz-hero-subtitle {{
    font-size: 12px;
    color: {KYTH_TEXT_MUTED};
}}

QLabel#glowing-pill-ok {{
    background-color: rgba(16, 185, 129, 30);
    border: 1px solid {STATUS_OK};
    color: {STATUS_OK};
    border-radius: 12px;
    padding: 5px 12px;
    font-size: 11px;
    font-weight: 800;
}}

QLabel#glowing-pill-warn {{
    background-color: rgba(245, 158, 11, 30);
    border: 1px solid {STATUS_WARN};
    color: {STATUS_WARN};
    border-radius: 12px;
    padding: 5px 12px;
    font-size: 11px;
    font-weight: 800;
}}

QFrame#genz-hud-card {{
    background-color: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 10px;
}}

QFrame#genz-hud-card:hover {{
    background-color: {KYTH_SURFACE_RAISED};
    border-color: {KYTH_HAIRLINE};
}}

QLabel#hud-title {{
    color: {KYTH_TEXT};
    font-size: 14px;
    font-weight: 750;
}}

QLabel#hud-desc {{
    color: {KYTH_TEXT_MUTED};
    font-size: 12px;
}}

QFrame#genz-category-card,
QFrame#genz-category-gaming,
QFrame#genz-category-apps,
QFrame#genz-category-system,
QFrame#genz-category-network,
QFrame#genz-category-advanced {{
    background-color: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-left: 3px solid transparent;
    border-radius: 14px;
}}

QFrame#genz-category-card:hover,
QFrame#genz-category-gaming:hover,
QFrame#genz-category-apps:hover,
QFrame#genz-category-system:hover,
QFrame#genz-category-network:hover,
QFrame#genz-category-advanced:hover {{
    background-color: {KYTH_SURFACE_RAISED};
    border-left-color: {KYTH_BLUE};
}}

QPushButton#genz-category-title {{
    background: transparent;
    color: {KYTH_TEXT};
    border: none;
    padding: 0;
    font-size: 16px;
    font-weight: 750;
    text-align: left;
}}

QPushButton#genz-category-title:hover {{
    color: {KYTH_BLUE_LIGHT};
}}

QPushButton#genz-task-link {{
    background: transparent;
    color: {KYTH_BLUE_LIGHT};
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
    font-weight: 600;
    text-align: left;
}}

QPushButton#genz-task-link:hover {{
    background-color: {KYTH_HAIRLINE};
    color: {KYTH_TEXT};
}}

/* Semantic styles for consistent layout property grids */
QLabel#prop-key {{
    color: {KYTH_TEXT_MUTED};
}}

QLabel#prop-val {{
    color: {KYTH_TEXT};
}}

QLabel#prop-val-dim {{
    color: {KYTH_TEXT_FAINT};
}}

QLabel#prop-val-green {{
    color: {STATUS_OK};
    font-weight: bold;
}}

QLabel#prop-val-red {{
    color: {STATUS_ERROR};
    font-weight: bold;
}}

QLabel#prop-val-orange {{
    color: {STATUS_WARN};
    font-weight: bold;
}}

QLabel#prop-val-blue {{
    color: {KYTH_BLUE_LIGHT};
    font-weight: bold;
}}

QLabel#h2-heading {{
    font-size: 18px;
    font-weight: 750;
    color: {KYTH_TEXT};
}}

QLabel#caption-text {{
    font-size: 12px;
    color: {KYTH_TEXT_MUTED};
}}
"""
