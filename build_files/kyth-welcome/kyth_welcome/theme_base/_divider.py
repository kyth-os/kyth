"""Divider — faint but present hairline separation."""

from ..ui_tokens import KYTH_HAIRLINE

DIVIDER_QSS = f"""
/* ── Divider ─────────────────────────────────────────────────────────────── */
QFrame#divider {{
    background: {KYTH_HAIRLINE};
    max-height: 1px;
    border: none;
}}
"""
