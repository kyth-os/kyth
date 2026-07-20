"""Category Grid QSS styles."""
from ..ui_tokens import (
    KYTH_BLUE, KYTH_BLUE_LIGHT, KYTH_HAIRLINE, KYTH_SURFACE,
    KYTH_SURFACE_RAISED, KYTH_TEXT, KYTH_TEXT_FAINT,
)

CATEGORY_GRID_QSS = f"""
/* ── Control Panel home: category grid ───────────────────────────────────── */
QFrame#cp-category {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 10px;
}}

QFrame#cp-category:hover {{
    background: {KYTH_SURFACE_RAISED};
    border-color: {KYTH_TEXT_FAINT};
}}

QPushButton#cp-category-title {{
    background: transparent;
    color: {KYTH_TEXT};
    border: none;
    padding: 0;
    font-size: 15px;
    font-weight: 600;
    text-align: left;
}}

QPushButton#cp-category-title:hover {{
    color: {KYTH_BLUE_LIGHT};
}}

QPushButton#task-link {{
    background: transparent;
    color: {KYTH_BLUE_LIGHT};
    border: none;
    border-radius: 4px;
    padding: 3px 6px;
    font-size: 12px;
    font-weight: 400;
    text-align: left;
}}

QPushButton#task-link:hover {{
    background: {KYTH_HAIRLINE};
    color: {KYTH_TEXT};
}}

QPushButton#task-link:pressed {{
    color: {KYTH_BLUE};
}}
"""
