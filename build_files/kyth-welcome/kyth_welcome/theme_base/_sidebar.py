"""Sidebar QSS styles."""

SIDEBAR_QSS = """
/* ── Sidebar ─────────────────────────────────────────────────────────────── */
QWidget#sidebar {
    background: #0c0e16;
    border-right: 1px solid #1e2230;
    border-left: 4px solid #4f8cff;
}

QWidget#sidebar-header {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1c253d, stop:1 #12141f);
    border-bottom: 1px solid #1e2230;
}

QLabel#sidebar-logo {
    font-size: 20px;
    font-weight: 700;
    color: #ffffff;
    padding: 0;
}

QLabel#sidebar-ver {
    font-size: 11px;
    color: #a6a6a6;
    font-weight: 500;
    padding: 0;
}

QLabel#nav-section {
    font-size: 11px;
    font-weight: 600;
    color: #8a8a8a;
    padding: 0 0 2px 0;
}

QPushButton#nav-item,
QPushButton#nav-item-active {
    background: transparent;
    border: none;
    border-radius: 6px;
    margin: 1px 8px;
    padding: 8px 10px;
    text-align: left;
    font-size: 13px;
}

QPushButton#nav-item {
    color: #d6d6d6;
    font-weight: 400;
}

QPushButton#nav-item:hover {
    background: #181b28;
    color: #ffffff;
}

QPushButton#nav-item:pressed {
    background: #1e2230;
}

QPushButton#nav-item-active {
    background: #181b28;
    color: #ffffff;
    border-left: 3px solid #8fb8ff;
    padding: 8px 10px 8px 7px;
    font-weight: 600;
}
"""
