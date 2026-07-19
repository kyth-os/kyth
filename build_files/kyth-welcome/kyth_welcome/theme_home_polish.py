"""Home page polish pass: transparent text, structure moved to panels."""

HOME_POLISH_QSS = """
/* Home polish pass: keep text transparent and move structure to panels. */
QWidget#page,
QScrollArea,
QScrollArea > QWidget,
QWidget#scroll-content {
    background: #0c0e16;
}

QLabel {
    background: transparent;
}

QFrame#card,
QFrame#card-accent-ok,
QFrame#card-accent-warn,
QFrame#stat-tile,
QFrame#summary-tile,
QFrame#home-action,
QFrame#home-section-header {
    background: #151722;
    border: 1px solid #26293a;
    border-radius: 8px;
}

QFrame#card,
QFrame#home-section-header {
    padding: 0;
}


QFrame#stat-tile {
    background: #151722;
    border-color: #44494c;
}

QFrame#stat-tile:hover,
QFrame#summary-tile:hover,
QFrame#home-action:hover {
    background: #1f2335;
    border-color: #5a666b;
}

QLabel#home-section-title {
    color: #f4f7f8;
    font-size: 20px;
    font-weight: 700;
}

QLabel#home-section-subtitle,
QLabel#card-copy,
QLabel#stat-label {
    color: #b8c6cc;
}

QLabel#home-kicker {
    color: #8fb8ff;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
}

QLabel#stat-value {
    color: #f0f4f5;
    font-size: 16px;
    font-weight: 600;
}

QLabel#stat-value-ok {
    color: #8fd1ab;
}

QLabel#stat-value-warn {
    color: #e8c08a;
}

QPushButton#primary:hover {
    background: #8fb8ff;
}
"""
