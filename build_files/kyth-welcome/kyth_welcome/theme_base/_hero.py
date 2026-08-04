"""Hero/HUD/category cards and semantic property-grid labels — the Home
dashboard's "workstation mode" banner and category tiles.

The hero gradient and the five category accent hues are deliberately
bespoke wayfinding/personality color, not structural — anchored to
KYTH_VIOLET where it's already the closest match (Gaming's accent).
"""
from ..ui_tokens import (
    KYTH_BLUE, KYTH_BLUE_LIGHT, KYTH_HAIRLINE, KYTH_SURFACE,
    KYTH_SURFACE_RAISED, KYTH_TEXT, KYTH_TEXT_FAINT, KYTH_TEXT_MUTED,
    KYTH_VIOLET, STATUS_ERROR, STATUS_OK, STATUS_WARN,
)

HERO_QSS = f"""
/* ── Hero / HUD / category cards ────────────────────────────────────────── */
QFrame#genz-hero {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1a1e29, stop:0.5 #281d3d, stop:1 #1c2b36);
    border: 1px solid #483d73;
    border-radius: 16px;
}}

QLabel#genz-hero-title {{
    font-size: 28px;
    font-weight: 850;
    color: {KYTH_TEXT};
}}

QLabel#genz-hero-subtitle {{
    font-size: 13px;
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

QWidget#genz-focus-row {{
    background-color: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 12px;
}}

QPushButton#genz-mode-btn {{
    background-color: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 8px;
    color: {KYTH_TEXT_MUTED};
    font-weight: 750;
    padding: 8px 18px;
}}

QPushButton#genz-mode-btn:hover {{
    border-color: {KYTH_BLUE};
    color: {KYTH_TEXT};
}}

QPushButton#genz-mode-btn:checked {{
    background-color: {KYTH_BLUE};
    border-color: {KYTH_BLUE_LIGHT};
    color: {KYTH_TEXT};
}}

QFrame#genz-hud-card {{
    background-color: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 14px;
}}

QFrame#genz-hud-card:hover {{
    border-color: {KYTH_BLUE};
    background-color: {KYTH_SURFACE_RAISED};
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
    border-radius: 14px;
}}

QFrame#genz-category-card:hover,
QFrame#genz-category-gaming:hover,
QFrame#genz-category-apps:hover,
QFrame#genz-category-system:hover,
QFrame#genz-category-network:hover,
QFrame#genz-category-advanced:hover {{
    background-color: {KYTH_SURFACE_RAISED};
}}

/* Category accents are wayfinding color, not status — five distinct hues on
   purpose. Gaming reuses KYTH_VIOLET; the rest stay bespoke. */
QFrame#genz-category-gaming {{
    border-left: 5px solid {KYTH_VIOLET};
}}

QFrame#genz-category-apps {{
    border-left: 5px solid #06b6d4;
}}

QFrame#genz-category-system {{
    border-left: 5px solid {STATUS_OK};
}}

QFrame#genz-category-network {{
    border-left: 5px solid {STATUS_WARN};
}}

QFrame#genz-category-advanced {{
    border-left: 5px solid #ec4899;
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
