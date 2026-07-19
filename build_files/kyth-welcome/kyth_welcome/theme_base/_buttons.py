"""Buttons QSS styles."""

BUTTONS_QSS = """
/* ── Buttons ─────────────────────────────────────────────────────────────── */
QPushButton {
    background: #181b28;
    color: #e8e8e8;
    border: 1px solid #26293a;
    border-radius: 5px;
    padding: 7px 16px;
    font-size: 13px;
    font-weight: 400;
}

QPushButton:hover {
    background: #1f2335;
    color: #ffffff;
    border-color: #454545;
}

QPushButton:pressed {
    background: #1e2230;
    color: #cfcfcf;
}

QPushButton:disabled {
    background: #12141f;
    color: #6b6b6b;
    border-color: #303030;
}

QPushButton#primary,
QPushButton#btn-secondary {
    background: #4f8cff;
    color: #ffffff;
    border: 1px solid #8fb8ff;
    font-weight: 600;
    padding: 8px 20px;
    letter-spacing: 0.3px;
}

QPushButton#primary:hover,
QPushButton#btn-secondary:hover {
    background: #8fb8ff;
    border-color: #8fb8ff;
}

QPushButton#primary:pressed,
QPushButton#btn-secondary:pressed {
    background: #3a6fd1;
}

QPushButton#primary:disabled,
QPushButton#btn-secondary:disabled {
    background: #181b28;
    color: #6b6b6b;
    border-color: #303030;
}

QPushButton#danger {
    background: #c42b1c;
    color: #ffffff;
    border: 1px solid #d13438;
    font-weight: 600;
}

QPushButton#danger:hover {
    background: #d13438;
    border-color: #ff6b6b;
}

QPushButton#danger:pressed {
    background: #a72015;
}

QPushButton#danger:disabled {
    background: #2d1d1c;
    color: #6b5252;
    border-color: #3a2a29;
}

QPushButton#branch-active {
    background: #4f8cff;
    color: #ffffff;
    font-weight: 600;
    border: 1px solid #8fb8ff;
    border-radius: 5px;
    padding: 9px 22px;
}

QPushButton#branch-inactive {
    background: #181b28;
    color: #a6a6a6;
    border: 1px solid #26293a;
    border-radius: 5px;
    padding: 9px 22px;
}

QPushButton#branch-inactive:hover {
    background: #1f2335;
    color: #e8e8e8;
    border-color: #454545;
}
"""
