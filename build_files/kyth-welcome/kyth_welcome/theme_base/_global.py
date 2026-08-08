"""Global — layered dark canvas with Windows/Steam depth.

Keep the window canvas solid dark; depth comes from surface layering, not a
gradient wash (Qt's viewport widget would otherwise paint black/white gaps on
offscreen renders). Labels stay transparent so they float over cards.
"""
from ..ui_tokens import KYTH_GROUND, KYTH_HAIRLINE_LIGHT, KYTH_SURFACE_RAISED, KYTH_TEXT

GLOBAL_QSS = f"""
* {{
    font-family: "Segoe UI Variable", "Segoe UI", "Noto Sans", "Cantarell", sans-serif;
    font-size: 13px;
    color: {KYTH_TEXT};
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
    background: {KYTH_GROUND};
    border: none;
}}

QToolTip {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT};
    border: 1px solid {KYTH_HAIRLINE_LIGHT};
    padding: 7px 12px;
    border-radius: 8px;
    font-size: 12px;
}}

/* Focus — visible keyboard ring on interactive controls */
QPushButton:focus, QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
    outline: none;
}}
"""
