"""Inputs — Windows Settings inset fields with blue focus ring."""

from ..ui_tokens import KYTH_BLUE, KYTH_BLUE_LIGHT, KYTH_HAIRLINE, KYTH_HAIRLINE_LIGHT, KYTH_RADIUS_SM, KYTH_SURFACE, KYTH_SURFACE_OVERLAY, KYTH_SURFACE_RAISED, KYTH_TEXT, KYTH_TEXT_FAINT

INPUTS_QSS = f"""
/* ── Inputs ──────────────────────────────────────────────────────────────── */
QLineEdit,
QTextEdit,
QComboBox,
QSpinBox {{
    background: {KYTH_SURFACE_RAISED};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS_SM}px;
    padding: 7px 9px;
    color: {KYTH_TEXT};
    selection-background-color: {KYTH_BLUE};
    selection-color: #ffffff;
}}

QLineEdit:focus,
QTextEdit:focus,
QComboBox:focus,
QSpinBox:focus {{
    border-color: {KYTH_BLUE};
    background: {KYTH_SURFACE_OVERLAY};
}}

QLineEdit:hover,
QTextEdit:hover,
QComboBox:hover {{
    border-color: {KYTH_HAIRLINE_LIGHT};
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
    min-width: 80px;
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
