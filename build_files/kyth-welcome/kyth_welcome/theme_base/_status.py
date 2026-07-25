"""Status QSS styles.

Kyth Theme: tokenized. task-status-idle/running have no theme_hub_overlay.py
equivalent (it only overrides ok/warn/err/dim) and remain fully load-bearing.
"""
from ..ui_tokens import (
    KYTH_BLUE_DIM, KYTH_BLUE_LIGHT, KYTH_HAIRLINE, KYTH_SURFACE,
    KYTH_SURFACE_RAISED, KYTH_TEXT, KYTH_TEXT_FAINT, KYTH_TEXT_MUTED,
    STATUS_ERROR, STATUS_OK, STATUS_WARN,
)

STATUS_QSS = f"""
/* ── Status labels ───────────────────────────────────────────────────────── */
QLabel#status-ok {{
    color: {STATUS_OK};
    font-weight: 600;
}}

QLabel#status-warn {{
    color: {STATUS_WARN};
    font-weight: 600;
}}

QLabel#status-err {{
    color: {STATUS_ERROR};
    font-weight: 600;
}}

QLabel#status-dim {{
    color: {KYTH_TEXT_FAINT};
}}

QLabel#task-status-idle,
QLabel#task-status-running,
QLabel#task-status-ok,
QLabel#task-status-warn,
QLabel#task-status-err {{
    border-radius: 5px;
    padding: 8px 10px;
    font-weight: 600;
}}

QLabel#task-status-idle {{
    background: {KYTH_SURFACE};
    color: {KYTH_TEXT_MUTED};
    border: 1px solid {KYTH_HAIRLINE};
}}

QLabel#task-status-running {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_BLUE_LIGHT};
    border: 1px solid {KYTH_BLUE_DIM};
}}

QLabel#task-status-ok {{
    background: rgba(16, 185, 129, 20);
    color: {STATUS_OK};
    border: 1px solid {STATUS_OK};
}}

QLabel#task-status-warn {{
    background: rgba(245, 158, 11, 20);
    color: {STATUS_WARN};
    border: 1px solid {STATUS_WARN};
}}

QLabel#task-status-err {{
    background: rgba(247, 118, 142, 20);
    color: {STATUS_ERROR};
    border: 1px solid {STATUS_ERROR};
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
    border-radius: 6px;
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
    border-radius: 6px;
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
"""
