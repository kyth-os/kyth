"""Inputs QSS styles.

Kyth Theme: tokenized. QCheckBox/QComboBox have no theme_hub_overlay.py
equivalent and remain fully load-bearing (this is what styles the wizard's
plain QCheckBox rows on the Get Apps step, for one).
"""
from ..ui_tokens import (
    KYTH_BLUE, KYTH_BLUE_LIGHT, KYTH_HAIRLINE, KYTH_SURFACE,
    KYTH_SURFACE_RAISED, KYTH_TEXT, KYTH_TEXT_FAINT,
)

INPUTS_QSS = f"""
/* ── Inputs ──────────────────────────────────────────────────────────────── */
QLineEdit {{
    background: {KYTH_SURFACE_RAISED};
    border: 1px solid {KYTH_HAIRLINE};
    border-bottom: 1px solid {KYTH_TEXT_FAINT};
    border-radius: 5px;
    padding: 7px 11px;
    color: {KYTH_TEXT};
    selection-background-color: {KYTH_HAIRLINE};
}}

QLineEdit:focus {{
    background: {KYTH_SURFACE_RAISED};
    border-bottom: 2px solid {KYTH_BLUE_LIGHT};
}}

QCheckBox {{
    color: {KYTH_TEXT};
    spacing: 9px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    background: {KYTH_SURFACE_RAISED};
    border: 1px solid {KYTH_TEXT_FAINT};
    border-radius: 4px;
}}

QCheckBox::indicator:checked {{
    background: {KYTH_BLUE};
    border-color: {KYTH_BLUE};
}}

QCheckBox::indicator:hover {{
    border-color: {KYTH_BLUE_LIGHT};
}}

QComboBox {{
    background: {KYTH_SURFACE_RAISED};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 5px;
    padding: 7px 11px;
    color: {KYTH_TEXT};
    min-width: 80px;
}}

QComboBox:hover {{
    border-color: {KYTH_TEXT_FAINT};
    background: {KYTH_SURFACE_RAISED};
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

QComboBox QAbstractItemView {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    color: {KYTH_TEXT};
    selection-background-color: {KYTH_SURFACE_RAISED};
    outline: none;
}}
"""
