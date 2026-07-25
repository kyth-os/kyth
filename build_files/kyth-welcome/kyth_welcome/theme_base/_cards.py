"""Cards QSS styles.

Kyth Theme: tokenized. #card/#card-accent-*/#card-title/#card-summary/
#card-copy are also set by theme_hub_overlay.py (wins, later in cascade) —
kept here in sync on the same tokens rather than removed, since this file's
other selectors (home-recommend-card, store-*, drop-*, home-action-*,
home-next-*, starter-pack-*) have no overlay equivalent and are load-bearing.
"""
from ..ui_tokens import (
    KYTH_BLUE, KYTH_BLUE_DIM, KYTH_BLUE_LIGHT, KYTH_HAIRLINE, KYTH_SURFACE,
    KYTH_SURFACE_RAISED, KYTH_TEXT, KYTH_TEXT_FAINT, KYTH_TEXT_MUTED,
    STATUS_ERROR, STATUS_OK, STATUS_WARN,
)

CARDS_QSS = f"""
/* ── Cards ───────────────────────────────────────────────────────────────── */
QFrame#card,
QFrame#home-recommend-card,
QFrame#home-action-card,
QFrame#stat-tile,
QFrame#starter-pack,
QFrame#ready-panel,
QFrame#store-app-card,
QFrame#store-category-card {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 10px;
}}

QFrame#card:hover,
QFrame#home-recommend-card:hover,
QFrame#home-action-card:hover,
QFrame#stat-tile:hover,
QFrame#store-app-card:hover,
QFrame#store-category-card:hover {{
    background: {KYTH_SURFACE_RAISED};
    border-color: {KYTH_TEXT_FAINT};
}}

QLabel#card-title {{
    font-size: 14px;
    font-weight: 600;
    color: {KYTH_TEXT};
}}

QLabel#card-subtitle {{
    font-size: 13px;
    font-weight: 600;
    color: {KYTH_TEXT};
}}

QLabel#card-summary {{
    color: {KYTH_TEXT};
    font-weight: 600;
}}

QLabel#card-action {{
    color: {KYTH_BLUE_LIGHT};
}}

QLabel#card-copy {{
    color: {KYTH_TEXT_MUTED};
}}

QFrame#home-recommend-card {{
    background: {KYTH_SURFACE_RAISED};
    border: 1px solid {KYTH_BLUE_DIM};
    border-left: 5px solid {KYTH_BLUE};
    border-radius: 10px;
}}

QLabel#home-kicker {{
    color: {KYTH_BLUE_LIGHT};
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1.5px;
}}

QFrame#home-section {{
    background: transparent;
    border: none;
}}

QLabel#home-section-title {{
    color: {KYTH_TEXT};
    font-size: 15px;
    font-weight: 700;
}}

QLabel#home-section-copy {{
    color: {KYTH_TEXT_FAINT};
    font-size: 12px;
}}

QFrame#card-accent-ok {{
    background: rgba(16, 185, 129, 20);
    border: 1px solid {STATUS_OK};
    border-radius: 10px;
}}

QFrame#card-accent-warn {{
    background: rgba(245, 158, 11, 20);
    border: 1px solid {STATUS_WARN};
    border-radius: 10px;
}}

QFrame#card-accent-err {{
    background: rgba(247, 118, 142, 20);
    border: 1px solid {STATUS_ERROR};
    border-radius: 10px;
}}

QLabel#home-action-icon {{
    font-size: 13px;
    font-weight: 600;
    color: {KYTH_BLUE_LIGHT};
}}

QLabel#home-action-title {{
    font-size: 15px;
    font-weight: 600;
    color: {KYTH_TEXT};
}}

QLabel#home-action-copy {{
    color: {KYTH_TEXT_MUTED};
}}

QLabel#home-next-title {{
    font-size: 24px;
    font-weight: 750;
    color: {KYTH_TEXT};
}}

QLabel#home-next-copy {{
    color: {KYTH_TEXT_MUTED};
}}

QLabel#home-next-meta {{
    color: {KYTH_BLUE_LIGHT};
}}

QPushButton#starter-pack-header {{
    background: transparent;
    border: none;
    color: {KYTH_TEXT};
    text-align: left;
    font-size: 14px;
    font-weight: 600;
    padding: 0;
}}

QPushButton#starter-pack-header:hover {{
    color: {KYTH_BLUE_LIGHT};
}}

QLabel#starter-pack-meta {{
    color: {KYTH_BLUE_LIGHT};
    font-size: 11px;
    font-weight: 600;
}}

QWidget#starter-pack-details {{
    background: transparent;
}}

QFrame#store-hero {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 6px;
}}

QLabel#store-hero-title {{
    font-size: 20px;
    font-weight: 600;
    color: {KYTH_TEXT};
}}

QLabel#store-kicker {{
    color: {KYTH_BLUE_LIGHT};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}}

QFrame#drop-card {{
    background: {KYTH_SURFACE};
    border: 1px dashed {KYTH_HAIRLINE};
    border-radius: 10px;
}}

QFrame#drop-card-active {{
    background: {KYTH_SURFACE_RAISED};
    border: 2px dashed {KYTH_BLUE_LIGHT};
    border-radius: 10px;
}}

QLabel#drop-glyph {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_BLUE_LIGHT};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 8px;
    font-size: 12px;
    font-weight: 600;
}}

QLabel#drop-title {{
    font-size: 18px;
    font-weight: 600;
    color: {KYTH_TEXT};
}}
"""
