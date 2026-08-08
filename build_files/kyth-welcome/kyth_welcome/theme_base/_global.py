"""Global QSS styles — the whole app's base surface, text, and scroll rules.

QWidget's real background is KYTH_GROUND, not transparent: a page's root
QWidget must paint the window color itself (Qt doesn't fill it for you),
which is why this used to live in theme_hub_overlay.py "applied after the
base theme so every hub page uses the same surface... without touching
page behavior" — folded in directly now that there's only one pass.
"""
from ..ui_tokens import KYTH_GROUND, KYTH_HAIRLINE, KYTH_SURFACE, KYTH_SURFACE_RAISED, KYTH_TEXT

GLOBAL_QSS = f"""
* {{
    font-family: "Segoe UI Variable", "Segoe UI", "Noto Sans", "Cantarell", sans-serif;
    font-size: 13px;
    color: {KYTH_TEXT};
}}
@media (prefers-reduced-motion: reduce) {{
    * {{ transition: none; }}
}}

QMainWindow,
QWidget#content-area {{
    background: {KYTH_GROUND};
}}

QWidget {{
    background-color: {KYTH_GROUND};
    color: {KYTH_TEXT};
}}

QLabel {{
    background: transparent;
}}

QScrollArea,
QScrollArea > QWidget > QWidget {{
    background: transparent;
    border: none;
}}

QToolTip {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT};
    border: 1px solid {KYTH_HAIRLINE};
    padding: 6px 10px;
    border-radius: 6px;
}}

/* Focus — visible keyboard ring on interactive controls */
QPushButton:focus, QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
    outline: none;
}}
"""
