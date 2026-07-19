"""Switcher QSS styles."""

SWITCHER_QSS = """
/* ── Gaming section switcher ─────────────────────────────────────────────── */
QFrame#gaming-section-switcher {
    background: transparent;
    border: none;
}

QWidget#gaming-section-row {
    background: transparent;
}

QPushButton#gaming-section,
QPushButton#gaming-section-active {
    border-radius: 5px;
    padding: 7px 14px;
    font-weight: 600;
}

QPushButton#gaming-section {
    background: #151722;
    color: #a6a6a6;
    border: 1px solid #26293a;
}

QPushButton#gaming-section:hover {
    background: #181b28;
    color: #ffffff;
    border-color: #2e324c;
}

QPushButton#gaming-section-active {
    background: #1c253d;
    color: #ffffff;
    border: 1px solid #8fb8ff;
}
"""
