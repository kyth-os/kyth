"""Topbar QSS styles."""

TOPBAR_QSS = """
/* ── Top command bar ─────────────────────────────────────────────────────── */
QWidget#topbar {
    background: #12141f;
    border-bottom: 1px solid #1e2230;
}

QPushButton#topbar-nav {
    background: transparent;
    color: #e8e8e8;
    border: none;
    border-radius: 5px;
    padding: 4px 0;
    font-size: 15px;
    font-weight: 400;
}

QPushButton#topbar-nav:hover {
    background: #181b28;
}

QPushButton#topbar-nav:pressed {
    background: #1e2230;
}

QPushButton#topbar-nav:disabled {
    color: #5c5c5c;
    background: transparent;
}

QPushButton#breadcrumb-link {
    background: transparent;
    color: #e8e8e8;
    border: none;
    border-radius: 5px;
    padding: 4px 8px;
    font-size: 13px;
    font-weight: 600;
    text-align: left;
}

QPushButton#breadcrumb-link:hover {
    background: #181b28;
    color: #ffffff;
}

QLabel#breadcrumb {
    color: #a6a6a6;
    font-size: 13px;
}

QLineEdit#search-box {
    background: #181b28;
    color: #e8e8e8;
    border: 1px solid #26293a;
    border-bottom: 1px solid #5c5c5c;
    border-radius: 5px;
    padding: 6px 12px;
}

QLineEdit#search-box:focus {
    background: #1f1f1f;
    border-bottom: 2px solid #8fb8ff;
}

QFrame#search-results-panel {
    background: #12141f;
    border-bottom: 1px solid #1e2230;
}

QLabel#search-results-title {
    color: #ffffff;
    font-size: 12px;
    font-weight: 700;
}

QLabel#search-results-hint {
    color: #8a8a8a;
    font-size: 11px;
}

QPushButton#search-result {
    background: #151722;
    color: #dcdcdc;
    border: 1px solid #26293a;
    border-radius: 6px;
    padding: 8px 12px;
    text-align: left;
    font-size: 12px;
    line-height: 1.35;
}

QPushButton#search-result:hover {
    background: #181b28;
    color: #ffffff;
    border-color: #2e324c;
}

QPushButton#search-result:pressed {
    background: #0c0e16;
}
"""
