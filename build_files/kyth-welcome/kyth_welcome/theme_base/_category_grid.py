"""Category Grid QSS styles."""

CATEGORY_GRID_QSS = """
/* ── Control Panel home: category grid ───────────────────────────────────── */
QFrame#cp-category {
    background: #151722;
    border: 1px solid #26293a;
    border-radius: 10px;
}

QFrame#cp-category:hover {
    background: #1f2335;
    border-color: #2e324c;
}

QPushButton#cp-category-title {
    background: transparent;
    color: #ffffff;
    border: none;
    padding: 0;
    font-size: 15px;
    font-weight: 600;
    text-align: left;
}

QPushButton#cp-category-title:hover {
    color: #8fb8ff;
}

QPushButton#task-link {
    background: transparent;
    color: #8fb8ff;
    border: none;
    border-radius: 4px;
    padding: 3px 6px;
    font-size: 12px;
    font-weight: 400;
    text-align: left;
}

QPushButton#task-link:hover {
    background: #383838;
    color: #c2d9ff;
}

QPushButton#task-link:pressed {
    color: #4f8cff;
}
"""
