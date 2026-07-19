"""Tab Bar QSS styles."""

TAB_BAR_QSS = """
/* ── Software page tab bar ───────────────────────────────────────────────── */
QWidget#sw-tab-bar {
    background: #12141f;
}

QPushButton#sw-tab,
QPushButton#sw-tab-active {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 10px 22px;
    font-size: 13px;
    min-width: 92px;
}

QPushButton#sw-tab {
    color: #a6a6a6;
    border-bottom: 2px solid transparent;
    font-weight: 400;
}

QPushButton#sw-tab:hover {
    background: #151722;
    color: #e8e8e8;
}

QPushButton#sw-tab-active {
    color: #ffffff;
    border-bottom: 2px solid #8fb8ff;
    font-weight: 600;
}
"""
