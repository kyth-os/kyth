"""Status QSS styles — inline status text, status/task pills, and empty/flow
step cards. Status pill backgrounds are a low-alpha tint of the same
STATUS_OK/WARN/ERROR text color, so they stay in lockstep without
hand-maintaining a separate set of dark-tinted hex values (Qt QSS rgba()
alpha is 0-255, not 0-100 — 30/255 ≈ 12% opacity).
"""
from ..ui_tokens import (
    KYTH_BLUE_DIM, KYTH_BLUE_LIGHT, KYTH_GROUND, KYTH_HAIRLINE, KYTH_RADIUS_SM, KYTH_SURFACE,
    KYTH_SURFACE_RAISED, KYTH_TEXT, KYTH_TEXT_FAINT, KYTH_TEXT_MUTED,
    STATUS_ERROR, STATUS_OK, STATUS_WARN,
)

_STATUS_OK_BG = "rgba(16, 185, 129, 30)"
_STATUS_WARN_BG = "rgba(245, 158, 11, 30)"
_STATUS_ERROR_BG = "rgba(247, 118, 142, 30)"

STATUS_QSS = f"""
/* ── Status labels ───────────────────────────────────────────────────────── */
QLabel#status-ok,
QLabel#task-status-ok {{
    background-color: {_STATUS_OK_BG};
    border: 1px solid {STATUS_OK};
    border-radius: {KYTH_RADIUS_SM}px;
    color: {STATUS_OK};
    font-weight: 600;
    padding: 4px 8px;
}}

QLabel#status-warn,
QLabel#task-status-warn {{
    background-color: {_STATUS_WARN_BG};
    border: 1px solid {STATUS_WARN};
    border-radius: {KYTH_RADIUS_SM}px;
    color: {STATUS_WARN};
    font-weight: 600;
    padding: 4px 8px;
}}

QLabel#status-err,
QLabel#task-status-err {{
    background-color: {_STATUS_ERROR_BG};
    border: 1px solid {STATUS_ERROR};
    border-radius: {KYTH_RADIUS_SM}px;
    color: {STATUS_ERROR};
    font-weight: 600;
    padding: 4px 8px;
}}

QLabel#status-dim,
QLabel#task-status-dim {{
    background-color: {KYTH_SURFACE_RAISED};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS_SM}px;
    color: {KYTH_TEXT_MUTED};
    padding: 4px 8px;
}}

QLabel#task-status-idle {{
    background: {KYTH_SURFACE};
    color: {KYTH_TEXT_MUTED};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS_SM}px;
    padding: 8px 10px;
    font-weight: 600;
}}

QLabel#task-status-running {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_BLUE_LIGHT};
    border: 1px solid {KYTH_BLUE_DIM};
    border-radius: {KYTH_RADIUS_SM}px;
    padding: 8px 10px;
    font-weight: 600;
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
    border: 1px dashed {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS_SM}px;
}}

QLabel#empty-state-title {{
    color: {KYTH_TEXT};
    font-size: 14px;
    font-weight: 700;
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
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_BLUE_LIGHT};
    border: 1px solid {KYTH_BLUE_DIM};
    border-radius: 10px;
    font-size: 11px;
    font-weight: 700;
}}

QLabel#flow-step-title {{
    color: {KYTH_TEXT};
    font-size: 13px;
    font-weight: 700;
}}

QLabel#flow-step-copy {{
    color: {KYTH_TEXT_MUTED};
}}

/* ── Launch-option key/value rows (Gaming Tools/Fixes) ──────────────────── */
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
    border-radius: 4px;
    padding: 3px 8px;
}}

QLabel#mono-inline {{
    font-family: "Cascadia Code", "Noto Mono", monospace;
    font-size: 12px;
    color: {KYTH_TEXT_MUTED};
}}

/* ── Plain inline status text (no pill/box — for warning notes, inline
   confirmations, etc. that sit next to normal body copy) ────────────────── */
QLabel#text-ok {{
    color: {STATUS_OK};
}}

QLabel#text-warn {{
    color: {STATUS_WARN};
}}

QLabel#text-err {{
    color: {STATUS_ERROR};
}}

QLabel#text-blue {{
    color: {KYTH_BLUE_LIGHT};
}}

/* ── Standalone glyph labels (✓/✗ marks with no pill background) ────────── */
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

/* ── Plasma/Wayland readiness info rows ─────────────────────────────────── */
QLabel#wayland-info-row {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS_SM}px;
    padding: 9px 11px;
    color: {KYTH_TEXT};
}}
"""
