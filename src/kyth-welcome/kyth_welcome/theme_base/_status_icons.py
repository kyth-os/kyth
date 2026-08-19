"""Fixed-size status-glyph QLabels (update/firmware check icons) — each
widget always renders at one font-size, only the state color changes, so a
handful of objectName variants replace what used to be inline
`setStyleSheet(f"font-size: Npx; color: {hex}")` calls scattered per state.
"""
from ..ui_tokens import KYTH_BLUE_LIGHT, KYTH_TEXT_FAINT, STATUS_OK, STATUS_WARN

STATUS_ICONS_QSS = f"""
/* ── Firmware-check icon (22px) ─────────────────────────────────────────── */
QLabel#fw-icon-dim {{
    font-size: 22px;
    color: {KYTH_TEXT_FAINT};
}}

QLabel#fw-icon-ok {{
    font-size: 22px;
    color: {STATUS_OK};
}}

QLabel#fw-icon-warn {{
    font-size: 22px;
    color: {STATUS_WARN};
}}

QLabel#fw-icon-blue {{
    font-size: 22px;
    color: {KYTH_BLUE_LIGHT};
}}

/* ── Update-availability icon (28px) ────────────────────────────────────── */
QLabel#avail-icon-dim {{
    font-size: 28px;
    color: {KYTH_TEXT_FAINT};
}}

QLabel#avail-icon-ok {{
    font-size: 28px;
    color: {STATUS_OK};
}}

QLabel#avail-icon-warn {{
    font-size: 28px;
    color: {STATUS_WARN};
}}

QLabel#avail-icon-blue {{
    font-size: 28px;
    color: {KYTH_BLUE_LIGHT};
}}
"""
