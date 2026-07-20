"""Global QSS styles."""
from ..ui_tokens import KYTH_GROUND, KYTH_HAIRLINE, KYTH_SURFACE, KYTH_TEXT

GLOBAL_QSS = f"""
* {{
    font-family: "Noto Sans", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {KYTH_TEXT};
}}

QMainWindow,
QWidget#content-area {{
    background: {KYTH_GROUND};
}}

QWidget {{
    background: transparent;
}}

QLabel {{
    background: transparent;
}}

QScrollArea {{
    background: transparent;
    border: none;
}}

QToolTip {{
    background: {KYTH_SURFACE};
    color: {KYTH_TEXT};
    border: 1px solid {KYTH_HAIRLINE};
    padding: 4px 8px;
}}
"""
