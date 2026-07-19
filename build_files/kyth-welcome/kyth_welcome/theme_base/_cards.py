"""Cards QSS styles."""

CARDS_QSS = """
/* ── Cards ───────────────────────────────────────────────────────────────── */
QFrame#card,
QFrame#home-recommend-card,
QFrame#home-action-card,
QFrame#stat-tile,
QFrame#starter-pack,
QFrame#ready-panel,
QFrame#store-app-card,
QFrame#store-category-card {
    background: #151722;
    border: 1px solid #26293a;
    border-radius: 10px;
}

QFrame#card:hover,
QFrame#home-recommend-card:hover,
QFrame#home-action-card:hover,
QFrame#stat-tile:hover,
QFrame#store-app-card:hover,
QFrame#store-category-card:hover {
    background: #1f2335;
    border-color: #2e324c;
}

QLabel#card-title {
    font-size: 14px;
    font-weight: 600;
    color: #ffffff;
}

QLabel#card-subtitle {
    font-size: 13px;
    font-weight: 600;
    color: #ffffff;
}

QLabel#card-summary {
    color: #e8e8e8;
    font-weight: 600;
}

QLabel#card-action {
    color: #8fb8ff;
}

QLabel#card-copy {
    color: #a6a6a6;
    line-height: 1.6;
}

QFrame#home-recommend-card {
    background: #1c253d;
    border: 1px solid #3d5d8a;
    border-left: 5px solid #4f8cff;
    border-radius: 10px;
}

QLabel#home-kicker {
    color: #8fb8ff;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1.5px;
}

QFrame#home-section {
    background: transparent;
    border: none;
}

QLabel#home-section-title {
    color: #ffffff;
    font-size: 15px;
    font-weight: 700;
}

QLabel#home-section-copy {
    color: #8a8a8a;
    font-size: 12px;
    line-height: 1.4;
}

QFrame#card-accent-ok {
    background: #0f2018;
    border: 1px solid #10b981;
    border-radius: 10px;
}

QFrame#card-accent-warn {
    background: #22160a;
    border: 1px solid #f59e0b;
    border-radius: 10px;
}

QFrame#card-accent-err {
    background: #271416;
    border: 1px solid #5e3338;
    border-radius: 10px;
}

QLabel#home-action-icon {
    font-size: 13px;
    font-weight: 600;
    color: #8fb8ff;
}

QLabel#home-action-title {
    font-size: 15px;
    font-weight: 600;
    color: #ffffff;
}

QLabel#home-action-copy {
    color: #a6a6a6;
    line-height: 1.45;
}

QLabel#home-next-title {
    font-size: 24px;
    font-weight: 750;
    color: #ffffff;
}

QLabel#home-next-copy {
    color: #c5c5c5;
    line-height: 1.5;
}

QLabel#home-next-meta {
    color: #c2d9ff;
    line-height: 1.45;
}

QPushButton#starter-pack-header {
    background: transparent;
    border: none;
    color: #ffffff;
    text-align: left;
    font-size: 14px;
    font-weight: 600;
    padding: 0;
}

QPushButton#starter-pack-header:hover {
    color: #8fb8ff;
}

QLabel#starter-pack-meta {
    color: #8fb8ff;
    font-size: 11px;
    font-weight: 600;
}

QWidget#starter-pack-details {
    background: transparent;
}

QFrame#store-hero {
    background: #151722;
    border: 1px solid #26293a;
    border-radius: 6px;
}

QLabel#store-hero-title {
    font-size: 20px;
    font-weight: 600;
    color: #ffffff;
}

QLabel#store-kicker {
    color: #8fb8ff;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}

QFrame#drop-card {
    background: #12141f;
    border: 1px dashed #2e324c;
    border-radius: 10px;
}

QFrame#drop-card-active {
    background: #1c253d;
    border: 2px dashed #8fb8ff;
    border-radius: 10px;
}

QLabel#drop-glyph {
    background: #181b28;
    color: #8fb8ff;
    border: 1px solid #26293a;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 600;
}

QLabel#drop-title {
    font-size: 18px;
    font-weight: 600;
    color: #ffffff;
}
"""
