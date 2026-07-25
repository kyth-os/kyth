"""Modern System Hub overlay pass — applied after the base theme so every
hub page shares the same surface, spacing, control, and status language.

Kyth Theme: tokenized (ui_tokens.KYTH_*) so this pass — which wins for
nearly every widget in the app via bare-type selectors below, applied last
in the cascade — finally shares one palette with the wizard (wizard/) and
Hub shell (_sidebar.py/_topbar.py) instead of carrying its own separate
values. STATUS_OK/WARN/ERROR are the same tokens widgets.py's StatusBadge
uses, so a status pill looks the same whether it's drawn by this pass or by
Python-side inline styling.
"""
from .ui_tokens import (
    KYTH_BLUE, KYTH_BLUE_LIGHT, KYTH_GROUND, KYTH_HAIRLINE, KYTH_SURFACE,
    KYTH_SURFACE_RAISED, KYTH_TEXT, KYTH_TEXT_FAINT, KYTH_TEXT_MUTED,
    STATUS_ERROR, STATUS_OK, STATUS_WARN,
)

# Status label backgrounds are a low-alpha tint of the status color, so they
# stay in lockstep with STATUS_OK/WARN/ERROR above without hand-maintaining a
# separate set of dark-tinted hex values (Qt QSS rgba() alpha is 0-255).
_STATUS_OK_BG = "rgba(16, 185, 129, 30)"
_STATUS_WARN_BG = "rgba(245, 158, 11, 30)"
_STATUS_ERROR_BG = "rgba(247, 118, 142, 30)"

HUB_OVERLAY_QSS = f"""
/* Modern System Hub overlay.
   Keep this after the base theme so every hub page uses the same surface,
   spacing, control, and status language without touching page behavior. */
QWidget {{
    background-color: {KYTH_GROUND};
    color: {KYTH_TEXT};
    font-size: 13px;
}}

QScrollArea,
QScrollArea > QWidget > QWidget {{
    background: transparent;
    border: 0;
}}

QFrame#card,
QFrame#card-accent-ok,
QFrame#card-accent-warn,
QFrame#card-accent-err,
QFrame#card-accent-dim,
QFrame#hw-card-dim {{
    background-color: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 8px;
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
    color: {KYTH_TEXT};
    font-size: 15px;
    font-weight: 700;
}}

QLabel#card-summary,
QLabel#subheading,
QLabel#page-subtitle,
QLabel#wizard-desc {{
    color: {KYTH_TEXT_MUTED};
}}

QLabel#page-eyebrow,
QLabel#eyebrow {{
    color: {KYTH_BLUE_LIGHT};
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0;
}}

QLabel#page-title,
QLabel#heading {{
    color: {KYTH_TEXT};
    font-size: 24px;
    font-weight: 750;
}}

QPushButton {{
    background-color: {KYTH_SURFACE_RAISED};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 6px;
    color: {KYTH_TEXT};
    font-weight: 650;
    padding: 8px 13px;
}}

QPushButton:hover {{
    background-color: {KYTH_HAIRLINE};
    border-color: {KYTH_TEXT_FAINT};
}}

QPushButton:pressed {{
    background-color: {KYTH_SURFACE};
}}

QPushButton:disabled {{
    background-color: {KYTH_GROUND};
    border-color: {KYTH_HAIRLINE};
    color: {KYTH_TEXT_FAINT};
}}

QPushButton#primary,
QPushButton[primary="true"] {{
    background-color: {KYTH_BLUE};
    border-color: {KYTH_BLUE};
    color: {KYTH_TEXT};
}}

QPushButton#primary:hover,
QPushButton[primary="true"]:hover {{
    background-color: {KYTH_BLUE_LIGHT};
}}

QLineEdit,
QTextEdit,
QComboBox,
QSpinBox {{
    background-color: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 6px;
    color: {KYTH_TEXT};
    padding: 7px 9px;
    selection-background-color: {KYTH_BLUE};
}}

QLineEdit:focus,
QTextEdit:focus,
QComboBox:focus,
QSpinBox:focus {{
    border-color: {KYTH_BLUE_LIGHT};
}}

QProgressBar {{
    background-color: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 6px;
    color: {KYTH_TEXT};
    text-align: center;
    min-height: 14px;
}}

QProgressBar::chunk {{
    background-color: {KYTH_BLUE};
    border-radius: 5px;
}}

QListWidget,
QListView {{
    background-color: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 8px;
    outline: 0;
}}

QListWidget::item,
QListView::item {{
    border-radius: 6px;
    margin: 3px 6px;
    padding: 8px 10px;
}}

QListWidget::item:selected,
QListView::item:selected {{
    background-color: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT};
}}

QLabel#status-ok,
QLabel#task-status-ok {{
    background-color: {_STATUS_OK_BG};
    border: 1px solid {STATUS_OK};
    border-radius: 6px;
    color: {STATUS_OK};
    padding: 4px 8px;
}}

QLabel#status-warn,
QLabel#task-status-warn {{
    background-color: {_STATUS_WARN_BG};
    border: 1px solid {STATUS_WARN};
    border-radius: 6px;
    color: {STATUS_WARN};
    padding: 4px 8px;
}}

QLabel#status-err,
QLabel#task-status-err {{
    background-color: {_STATUS_ERROR_BG};
    border: 1px solid {STATUS_ERROR};
    border-radius: 6px;
    color: {STATUS_ERROR};
    padding: 4px 8px;
}}

QLabel#status-dim,
QLabel#task-status-dim {{
    background-color: {KYTH_SURFACE_RAISED};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 6px;
    color: {KYTH_TEXT_MUTED};
    padding: 4px 8px;
}}
"""
