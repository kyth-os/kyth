"""Buttons — muted primary to match slate control-center theme.

Default is a soft raised pill (8px) with overlay hover. Primary previously
used a saturated #5b8cff fill that clashed with the slate ground/surface
layering — now a desaturated slate-blue (#263a54) with a subtle blue-gray
border, so it reads as primary without the neon pop. Hover lifts slightly to
#2e4566 with a brighter border. Destructive keeps its red.
"""
from ..ui_tokens import KYTH_BLUE, KYTH_DANGER, KYTH_DANGER_LIGHT, KYTH_GROUND, KYTH_HAIRLINE, KYTH_HAIRLINE_LIGHT, KYTH_PRIMARY_BG, KYTH_PRIMARY_BORDER, KYTH_PRIMARY_HOVER_BG, KYTH_PRIMARY_HOVER_BORDER, KYTH_PRIMARY_PRESSED_BG, KYTH_RADIUS_SM, KYTH_SURFACE, KYTH_SURFACE_OVERLAY, KYTH_SURFACE_RAISED, KYTH_TEXT, KYTH_TEXT_FAINT, KYTH_TEXT_MUTED

BUTTONS_QSS = f"""
/* ── Buttons ─────────────────────────────────────────────────────────────── */
QPushButton {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS_SM}px;
    padding: 7px 10px;
    font-size: 13px;
    font-weight: 600;
}}

QPushButton:hover {{
    background: {KYTH_SURFACE_OVERLAY};
    color: {KYTH_TEXT};
    border-color: {KYTH_HAIRLINE_LIGHT};
}}

QPushButton:focus {{
    border: 1px solid {KYTH_BLUE};
}}

QPushButton:pressed {{
    background: {KYTH_SURFACE};
    color: {KYTH_TEXT_MUTED};
}}

QPushButton:disabled {{
    background: {KYTH_GROUND};
    color: {KYTH_TEXT_FAINT};
    border-color: {KYTH_HAIRLINE};
}}

QPushButton#primary,
QPushButton#btn-secondary,
QPushButton[primary="true"] {{
    background: {KYTH_PRIMARY_BG};
    color: {KYTH_TEXT};
    border: 1px solid {KYTH_PRIMARY_BORDER};
    font-weight: 600;
    padding: 8px 14px;
    letter-spacing: 0.2px;
}}

QPushButton#primary:hover,
QPushButton#btn-secondary:hover,
QPushButton[primary="true"]:hover {{
    background: {KYTH_PRIMARY_HOVER_BG};
    border-color: {KYTH_PRIMARY_HOVER_BORDER};
    color: #ffffff;
}}

QPushButton#primary:pressed,
QPushButton#btn-secondary:pressed,
QPushButton[primary="true"]:pressed {{
    background: {KYTH_PRIMARY_PRESSED_BG};
    border-color: {KYTH_PRIMARY_BORDER};
}}

QPushButton#primary:disabled,
QPushButton#btn-secondary:disabled,
QPushButton[primary="true"]:disabled {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT_FAINT};
    border-color: {KYTH_HAIRLINE};
}}

QPushButton#danger {{
    background: {KYTH_DANGER};
    color: #ffffff;
    border: 1px solid {KYTH_DANGER_LIGHT};
    font-weight: 600;
}}

QPushButton#danger:hover {{
    background: {KYTH_DANGER_LIGHT};
    border-color: #ff6b6b;
}}

QPushButton#danger:pressed {{
    background: #a72015;
}}

QPushButton#danger:disabled {{
    background: #2d1d1c;
    color: #6b5252;
    border-color: #3a2a29;
}}

QPushButton#branch-active {{
    background: {KYTH_PRIMARY_BG};
    color: {KYTH_TEXT};
    font-weight: 600;
    border: 1px solid {KYTH_PRIMARY_BORDER};
    border-radius: {KYTH_RADIUS_SM}px;
    padding: 9px 22px;
}}

QPushButton#branch-inactive {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT_MUTED};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS_SM}px;
    padding: 9px 22px;
}}

QPushButton#branch-inactive:hover {{
    background: {KYTH_SURFACE_OVERLAY};
    color: {KYTH_TEXT};
    border-color: {KYTH_HAIRLINE_LIGHT};
}}
"""
