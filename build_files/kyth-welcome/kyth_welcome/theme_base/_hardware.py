"""Hardware QSS styles."""
from ..ui_tokens import (
    KYTH_HAIRLINE, KYTH_RADIUS, KYTH_SURFACE, KYTH_SURFACE_RAISED, KYTH_TEXT_FAINT,
    STATUS_ERROR, STATUS_OK, STATUS_WARN,
)

HARDWARE_QSS = f"""
/* ── Hardware cards ──────────────────────────────────────────────────────── */
QFrame#hw-card-ok {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-left: 4px solid {STATUS_OK};
    border-radius: {KYTH_RADIUS}px;
}}

QFrame#hw-card-ok:hover {{
    background: {KYTH_SURFACE_RAISED};
    border: 1px solid {KYTH_TEXT_FAINT};
    border-left: 4px solid {STATUS_OK};
    border-radius: {KYTH_RADIUS}px;
}}

QFrame#hw-card-warn {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-left: 4px solid {STATUS_WARN};
    border-radius: {KYTH_RADIUS}px;
}}

QFrame#hw-card-warn:hover {{
    background: {KYTH_SURFACE_RAISED};
    border: 1px solid {KYTH_TEXT_FAINT};
    border-left: 4px solid {STATUS_WARN};
    border-radius: {KYTH_RADIUS}px;
}}

QFrame#hw-card-err {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-left: 4px solid {STATUS_ERROR};
    border-radius: {KYTH_RADIUS}px;
}}

QFrame#hw-card-err:hover {{
    background: {KYTH_SURFACE_RAISED};
    border: 1px solid {KYTH_TEXT_FAINT};
    border-left: 4px solid {STATUS_ERROR};
    border-radius: {KYTH_RADIUS}px;
}}

QFrame#hw-card-dim {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-left: 4px solid {KYTH_TEXT_FAINT};
    border-radius: {KYTH_RADIUS}px;
}}

QFrame#hw-card-dim:hover {{
    background: {KYTH_SURFACE_RAISED};
    border: 1px solid {KYTH_TEXT_FAINT};
    border-left: 4px solid {KYTH_TEXT_FAINT};
    border-radius: {KYTH_RADIUS}px;
}}
"""
