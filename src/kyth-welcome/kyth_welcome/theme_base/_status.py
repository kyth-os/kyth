"""Status pills — subtle depth, tighter radius, clearer hierarchy.

Pills keep low-alpha tint but border is now 8px radius to match new button/card
language. Running/idle states use overlay surface so they pop a touch more.
"""

from ..ui_tokens import KYTH_BLUE_DIM, KYTH_BLUE_LIGHT, KYTH_GROUND, KYTH_HAIRLINE, KYTH_HAIRLINE_LIGHT, KYTH_RADIUS_SM, KYTH_SURFACE, KYTH_SURFACE_OVERLAY, KYTH_SURFACE_RAISED, KYTH_TEXT, KYTH_TEXT_FAINT, KYTH_TEXT_MUTED, STATUS_ERROR, STATUS_OK, STATUS_WARN

_STATUS_OK_BG = "rgba(16, 185, 129, 28)"
_STATUS_WARN_BG = "rgba(245, 158, 11, 28)"
_STATUS_ERROR_BG = "rgba(247, 118, 142, 28)"

STATUS_QSS = f"""
/* ── Status labels ───────────────────────────────────────────────────────── */
QLabel#status-ok,
QLabel#task-status-ok {{
    background-color: {_STATUS_OK_BG};
    border: 1px solid {STATUS_OK};
    border-radius: {KYTH_RADIUS_SM}px;
    color: {STATUS_OK};
    font-weight: 700;
    padding: 4px 9px;
}}

QLabel#status-warn,
QLabel#task-status-warn {{
    background-color: {_STATUS_WARN_BG};
    border: 1px solid {STATUS_WARN};
    border-radius: {KYTH_RADIUS_SM}px;
    color: {STATUS_WARN};
    font-weight: 700;
    padding: 4px 9px;
}}

QLabel#status-err,
QLabel#task-status-err {{
    background-color: {_STATUS_ERROR_BG};
    border: 1px solid {STATUS_ERROR};
    border-radius: {KYTH_RADIUS_SM}px;
    color: {STATUS_ERROR};
    font-weight: 700;
    padding: 4px 9px;
}}

QLabel#status-dim,
QLabel#task-status-dim {{
    background-color: {KYTH_SURFACE_RAISED};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS_SM}px;
    color: {KYTH_TEXT_MUTED};
    padding: 4px 9px;
}}

QLabel#task-status-idle {{
    background: {KYTH_SURFACE};
    color: {KYTH_TEXT_MUTED};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS_SM}px;
    padding: 8px 11px;
    font-weight: 600;
}}

QLabel#task-status-running {{
    background: {KYTH_SURFACE_OVERLAY};
    color: {KYTH_BLUE_LIGHT};
    border: 1px solid {KYTH_BLUE_DIM};
    border-radius: {KYTH_RADIUS_SM}px;
    padding: 8px 11px;
    font-weight: 700;
}}

QFrame#action-row {{
    background: transparent;
    border: none;
}}

QFrame#command-result-panel {{
    background: transparent;
    border: none;
}}

QFrame#empty-state {{
    background: {KYTH_SURFACE};
    border: 1px dashed {KYTH_HAIRLINE_LIGHT};
    border-radius: {KYTH_RADIUS_SM}px;
}}

QLabel#empty-state-title {{
    color: {KYTH_TEXT};
    font-size: 14px;
    font-weight: 700;
    letter-spacing: -0.2px;
}}

QLabel#empty-state-copy {{
    color: {KYTH_TEXT_MUTED};
}}

QFrame#flow-step {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS_SM}px;
}}

QLabel#flow-step-num {{
    background: {KYTH_SURFACE_OVERLAY};
    color: {KYTH_BLUE_LIGHT};
    border: 1px solid {KYTH_BLUE_DIM};
    border-radius: 10px;
    font-size: 11px;
    font-weight: 800;
}}

QLabel#flow-step-title {{
    color: {KYTH_TEXT};
    font-size: 13px;
    font-weight: 700;
}}

QLabel#flow-step-copy {{
    color: {KYTH_TEXT_MUTED};
}}

/* ── Launch-option key/value rows ───────────────────────────────────────── */
QLabel#launch-opt-label {{
    font-size: 12px;
    color: {KYTH_TEXT_FAINT};
}}

QLabel#launch-opt-value {{
    font-family: "Cascadia Code", "Noto Mono", monospace;
    font-size: 12px;
    color: {KYTH_TEXT};
    background: {KYTH_GROUND};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 6px;
    padding: 3px 8px;
}}

QLabel#mono-inline {{
    font-family: "Cascadia Code", "Noto Mono", monospace;
    font-size: 12px;
    color: {KYTH_TEXT_MUTED};
}}

QLabel#text-ok {{ color: {STATUS_OK}; }}
QLabel#text-warn {{ color: {STATUS_WARN}; }}
QLabel#text-err {{ color: {STATUS_ERROR}; }}
QLabel#text-blue {{ color: {KYTH_BLUE_LIGHT}; }}

QLabel#glyph-ok {{
    font-size: 18px;
    font-weight: 700;
    color: {STATUS_OK};
    background: transparent;
    border: none;
}}

QLabel#glyph-err {{
    font-size: 18px;
    font-weight: 700;
    color: {STATUS_ERROR};
    background: transparent;
    border: none;
}}

QLabel#glyph-finish-ok {{
    font-size: 52px;
    font-weight: 300;
    color: {STATUS_OK};
    background: transparent;
}}

QLabel#wayland-info-row {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS_SM}px;
    padding: 9px 11px;
    color: {KYTH_TEXT};
}}
"""
