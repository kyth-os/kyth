"""Category Grid — Control Panel tiles with layered hover."""

from ..ui_tokens import KYTH_BLUE, KYTH_BLUE_LIGHT, KYTH_HAIRLINE, KYTH_HAIRLINE_LIGHT, KYTH_SURFACE, KYTH_SURFACE_OVERLAY, KYTH_SURFACE_RAISED, KYTH_TEXT

CATEGORY_GRID_QSS = f"""
/* ── Control Panel home: category grid ───────────────────────────────────── */
QFrame#cp-category {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 12px;
}}

QFrame#cp-category:hover {{
    background: {KYTH_SURFACE_RAISED};
    border-color: {KYTH_HAIRLINE_LIGHT};
}}

QPushButton#cp-category-title {{
    background: transparent;
    color: {KYTH_TEXT};
    border: none;
    padding: 0;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: -0.2px;
    text-align: left;
}}

QPushButton#cp-category-title:hover {{
    color: {KYTH_BLUE_LIGHT};
}}

QPushButton#task-link {{
    background: transparent;
    color: {KYTH_BLUE_LIGHT};
    border: none;
    border-radius: 6px;
    padding: 3px 6px;
    font-size: 12px;
    font-weight: 500;
    text-align: left;
}}

QPushButton#task-link:hover {{
    background: {KYTH_SURFACE_OVERLAY};
    color: {KYTH_TEXT};
}}

QPushButton#task-link:pressed {{
    color: {KYTH_BLUE};
}}
"""
