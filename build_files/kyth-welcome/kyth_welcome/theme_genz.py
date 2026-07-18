"""Gen Z redesign styles: hero/HUD/category cards and semantic property-grid labels."""

GENZ_QSS = """
/* ── Gen Z Redesign Styles ──────────────────────────────────────────────── */
QFrame#genz-hero {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1a1e29, stop:0.5 #281d3d, stop:1 #1c2b36);
    border: 1px solid #483d73;
    border-radius: 16px;
}

QLabel#genz-hero-title {
    font-size: 28px;
    font-weight: 850;
    color: #ffffff;
}

QLabel#genz-hero-subtitle {
    font-size: 13px;
    color: #aab4bf;
}

QLabel#glowing-pill-ok {
    background-color: #0f2018;
    border: 1px solid #10b981;
    color: #34d399;
    border-radius: 12px;
    padding: 5px 12px;
    font-size: 11px;
    font-weight: 800;
}

QLabel#glowing-pill-warn {
    background-color: #22160a;
    border: 1px solid #f59e0b;
    color: #fbbf24;
    border-radius: 12px;
    padding: 5px 12px;
    font-size: 11px;
    font-weight: 800;
}

QWidget#genz-focus-row {
    background-color: #12141f;
    border: 1px solid #26293a;
    border-radius: 12px;
}

QPushButton#genz-mode-btn {
    background-color: #12141f;
    border: 1px solid #26293a;
    border-radius: 8px;
    color: #aab4bf;
    font-weight: 750;
    padding: 8px 18px;
}

QPushButton#genz-mode-btn:hover {
    border-color: #4f8cff;
    color: #ffffff;
}

QPushButton#genz-mode-btn:checked {
    background-color: #4f8cff;
    border-color: #8fb8ff;
    color: #ffffff;
}

QFrame#genz-hud-card {
    background-color: #151722;
    border: 1px solid #26293a;
    border-radius: 14px;
}

QFrame#genz-hud-card:hover {
    border-color: #4f8cff;
    background-color: #242933;
}

QLabel#hud-title {
    color: #ffffff;
    font-size: 14px;
    font-weight: 750;
}

QLabel#hud-desc {
    color: #aab4bf;
    font-size: 12px;
}

QFrame#genz-category-card,
QFrame#genz-category-gaming,
QFrame#genz-category-apps,
QFrame#genz-category-system,
QFrame#genz-category-network,
QFrame#genz-category-advanced {
    background-color: #151722;
    border: 1px solid #26293a;
    border-radius: 14px;
}

QFrame#genz-category-card:hover,
QFrame#genz-category-gaming:hover,
QFrame#genz-category-apps:hover,
QFrame#genz-category-system:hover,
QFrame#genz-category-network:hover,
QFrame#genz-category-advanced:hover {
    background-color: #242933;
}

QFrame#genz-category-gaming {
    border-left: 5px solid #a855f7;
}

QFrame#genz-category-apps {
    border-left: 5px solid #06b6d4;
}

QFrame#genz-category-system {
    border-left: 5px solid #10b981;
}

QFrame#genz-category-network {
    border-left: 5px solid #f59e0b;
}

QFrame#genz-category-advanced {
    border-left: 5px solid #ec4899;
}

QPushButton#genz-category-title {
    background: transparent;
    color: #ffffff;
    border: none;
    padding: 0;
    font-size: 16px;
    font-weight: 750;
    text-align: left;
}

QPushButton#genz-category-title:hover {
    color: #8fb8ff;
}

QPushButton#genz-task-link {
    background: transparent;
    color: #8fb8ff;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
    font-weight: 600;
    text-align: left;
}

QPushButton#genz-task-link:hover {
    background-color: #2b323c;
    color: #c2d9ff;
}

/* Semantic styles for consistent layout property grids */
QLabel#prop-key {
    color: #aab4bf;
}

QLabel#prop-val {
    color: #f4f6f8;
}

QLabel#prop-val-dim {
    color: #707985;
}

QLabel#prop-val-green {
    color: #34d399;
    font-weight: bold;
}

QLabel#prop-val-red {
    color: #ffb0b6;
    font-weight: bold;
}

QLabel#prop-val-orange {
    color: #fbbf24;
    font-weight: bold;
}

QLabel#prop-val-blue {
    color: #8fb8ff;
    font-weight: bold;
}

QLabel#h2-heading {
    font-size: 18px;
    font-weight: 750;
    color: #ffffff;
}

QLabel#caption-text {
    font-size: 12px;
    color: #aab4bf;
}
"""
