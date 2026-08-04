"""Cards QSS styles — the one #card family definition for the whole app.

Previously split: this file used a 10px radius, but theme_hub_overlay.py
and theme_home_polish.py each separately overrode #card/#card-accent-* to
8px (applied later in the cascade, so 8px is what actually rendered) while
this file's other card-shaped selectors (home-recommend-card, store-*,
starter-pack) stayed at 10px — two different radii rendering side by side
on the same page. Standardized on 10px everywhere; one radius token, one
visual family. #card-accent-ok/warn/err also used to be a fully tinted
background (this file's original) vs. a plain card with a colored
left-border stripe (theme_hub_overlay's, which won) — kept the left-stripe
treatment since it already matches #card-accent-dim/#hw-card-dim below and
reads as a settings card, not an alert box.
"""
from ..ui_tokens import (
    KYTH_BLUE, KYTH_BLUE_DIM, KYTH_BLUE_LIGHT, KYTH_HAIRLINE, KYTH_RADIUS,
    KYTH_RADIUS_SM, KYTH_SURFACE, KYTH_SURFACE_RAISED, KYTH_TEXT,
    KYTH_TEXT_FAINT, KYTH_TEXT_MUTED, STATUS_ERROR, STATUS_OK, STATUS_WARN,
)

CARDS_QSS = f"""
/* ── Cards ───────────────────────────────────────────────────────────────── */
QFrame#card,
QFrame#home-recommend-card,
QFrame#home-action-card,
QFrame#stat-tile,
QFrame#summary-tile,
QFrame#home-action,
QFrame#home-section-header,
QFrame#starter-pack,
QFrame#ready-panel,
QFrame#store-app-card,
QFrame#store-category-card,
QFrame#card-accent-ok,
QFrame#card-accent-warn,
QFrame#card-accent-err,
QFrame#card-accent-dim,
QFrame#hw-card-dim {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS}px;
}}

QFrame#card,
QFrame#home-section-header {{
    padding: 0;
}}

QFrame#card:hover,
QFrame#home-recommend-card:hover,
QFrame#home-action-card:hover,
QFrame#stat-tile:hover,
QFrame#summary-tile:hover,
QFrame#home-action:hover,
QFrame#store-app-card:hover,
QFrame#store-category-card:hover {{
    background: {KYTH_SURFACE_RAISED};
    border-color: {KYTH_TEXT_FAINT};
}}

QFrame#card-accent-ok {{
    border-left: 4px solid {STATUS_OK};
}}

QFrame#card-accent-warn {{
    border-left: 4px solid {STATUS_WARN};
}}

QFrame#card-accent-err {{
    border-left: 4px solid {STATUS_ERROR};
}}

QFrame#card-accent-dim,
QFrame#hw-card-dim {{
    border-left: 4px solid {KYTH_TEXT_FAINT};
}}

QLabel#card-title {{
    font-size: 15px;
    font-weight: 700;
    color: {KYTH_TEXT};
}}

QLabel#card-title-warn {{
    font-size: 15px;
    font-weight: 700;
    color: {STATUS_WARN};
}}

QLabel#card-title-err {{
    font-size: 15px;
    font-weight: 700;
    color: {STATUS_ERROR};
}}

QLabel#card-subtitle {{
    font-size: 13px;
    font-weight: 600;
    color: {KYTH_TEXT};
}}

QLabel#card-summary,
QLabel#subheading {{
    color: {KYTH_TEXT_MUTED};
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
    border-radius: {KYTH_RADIUS}px;
}}

QLabel#home-kicker {{
    color: {KYTH_BLUE_LIGHT};
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
}}

QFrame#home-section {{
    background: transparent;
    border: none;
}}

QLabel#home-section-title {{
    color: {KYTH_TEXT};
    font-size: 20px;
    font-weight: 700;
}}

QLabel#home-section-copy {{
    color: {KYTH_TEXT_FAINT};
    font-size: 12px;
}}

QLabel#home-action-icon {{
    font-size: 24px;
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
    border-radius: {KYTH_RADIUS}px;
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
    border-radius: {KYTH_RADIUS}px;
}}

QFrame#drop-card-active {{
    background: {KYTH_SURFACE_RAISED};
    border: 2px dashed {KYTH_BLUE_LIGHT};
    border-radius: {KYTH_RADIUS}px;
}}

QLabel#drop-glyph {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_BLUE_LIGHT};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS_SM}px;
    font-size: 12px;
    font-weight: 600;
}}

QLabel#drop-title {{
    font-size: 18px;
    font-weight: 600;
    color: {KYTH_TEXT};
}}
"""
