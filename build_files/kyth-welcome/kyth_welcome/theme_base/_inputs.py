"""Inputs QSS styles."""

INPUTS_QSS = """
/* ── Inputs ──────────────────────────────────────────────────────────────── */
QLineEdit {
    background: #181b28;
    border: 1px solid #26293a;
    border-bottom: 1px solid #5c5c5c;
    border-radius: 5px;
    padding: 7px 11px;
    color: #e8e8e8;
    selection-background-color: #1c253d;
}

QLineEdit:focus {
    background: #1f1f1f;
    border-bottom: 2px solid #8fb8ff;
}

QCheckBox {
    color: #e8e8e8;
    spacing: 9px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    background: #181b28;
    border: 1px solid #5c5c5c;
    border-radius: 4px;
}

QCheckBox::indicator:checked {
    background: #4f8cff;
    border-color: #4f8cff;
}

QCheckBox::indicator:hover {
    border-color: #8fb8ff;
}

QComboBox {
    background: #181b28;
    border: 1px solid #26293a;
    border-radius: 5px;
    padding: 7px 11px;
    color: #e8e8e8;
    min-width: 80px;
}

QComboBox:hover {
    border-color: #2e324c;
    background: #1f2335;
}

QComboBox::drop-down {
    border: none;
    width: 22px;
}

QComboBox QAbstractItemView {
    background: #151722;
    border: 1px solid #26293a;
    color: #e8e8e8;
    selection-background-color: #181b28;
    outline: none;
}
"""
