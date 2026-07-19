"""Modern System Hub overlay pass — applied after the base theme so every
hub page shares the same surface, spacing, control, and status language.
"""

HUB_OVERLAY_QSS = """
/* Modern System Hub overlay.
   Keep this after the base theme so every hub page uses the same surface,
   spacing, control, and status language without touching page behavior. */
QWidget {
    background-color: #0c0e16;
    color: #f4f6f8;
    font-size: 13px;
}

QScrollArea,
QScrollArea > QWidget > QWidget {
    background: transparent;
    border: 0;
}

QFrame#card,
QFrame#card-accent-ok,
QFrame#card-accent-warn,
QFrame#card-accent-err,
QFrame#card-accent-dim,
QFrame#hw-card-dim {
    background-color: #151722;
    border: 1px solid #26293a;
    border-radius: 8px;
}

QFrame#card-accent-ok {
    border-left: 4px solid #10b981;
}

QFrame#card-accent-warn {
    border-left: 4px solid #f59e0b;
}

QFrame#card-accent-err {
    border-left: 4px solid #e05f67;
}

QFrame#card-accent-dim,
QFrame#hw-card-dim {
    border-left: 4px solid #66717f;
}

QLabel#card-title {
    color: #ffffff;
    font-size: 15px;
    font-weight: 700;
}

QLabel#card-summary,
QLabel#subheading,
QLabel#page-subtitle,
QLabel#wizard-desc {
    color: #aab4bf;
}

QLabel#page-eyebrow,
QLabel#eyebrow {
    color: #8fb8ff;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0;
}

QLabel#page-title,
QLabel#heading {
    color: #ffffff;
    font-size: 24px;
    font-weight: 750;
}

QPushButton {
    background-color: #23282f;
    border: 1px solid #3b444f;
    border-radius: 6px;
    color: #f7f9fb;
    font-weight: 650;
    padding: 8px 13px;
}

QPushButton:hover {
    background-color: #2b323b;
    border-color: #53606d;
}

QPushButton:pressed {
    background-color: #1d2228;
}

QPushButton:disabled {
    background-color: #191c20;
    border-color: #2a2f36;
    color: #707985;
}

QPushButton#primary,
QPushButton[primary="true"] {
    background-color: #4f8cff;
    border-color: #3d5d8a;
    color: #ffffff;
}

QPushButton#primary:hover,
QPushButton[primary="true"]:hover {
    background-color: #8fb8ff;
}

QLineEdit,
QTextEdit,
QComboBox,
QSpinBox {
    background-color: #12141f;
    border: 1px solid #333a43;
    border-radius: 6px;
    color: #f4f6f8;
    padding: 7px 9px;
    selection-background-color: #4f8cff;
}

QLineEdit:focus,
QTextEdit:focus,
QComboBox:focus,
QSpinBox:focus {
    border-color: #8fb8ff;
}

QProgressBar {
    background-color: #12141f;
    border: 1px solid #333a43;
    border-radius: 6px;
    color: #f4f6f8;
    text-align: center;
    min-height: 14px;
}

QProgressBar::chunk {
    background-color: #4f8cff;
    border-radius: 5px;
}

QListWidget,
QListView {
    background-color: #12141f;
    border: 1px solid #26293a;
    border-radius: 8px;
    outline: 0;
}

QListWidget::item,
QListView::item {
    border-radius: 6px;
    margin: 3px 6px;
    padding: 8px 10px;
}

QListWidget::item:selected,
QListView::item:selected {
    background-color: #1c253d;
    color: #ffffff;
}

QLabel#status-ok,
QLabel#task-status-ok {
    background-color: #0f2018;
    border: 1px solid #10b981;
    border-radius: 6px;
    color: #34d399;
    padding: 4px 8px;
}

QLabel#status-warn,
QLabel#task-status-warn {
    background-color: #22160a;
    border: 1px solid #f59e0b;
    border-radius: 6px;
    color: #fbbf24;
    padding: 4px 8px;
}

QLabel#status-err,
QLabel#task-status-err {
    background-color: #271416;
    border: 1px solid #9f464f;
    border-radius: 6px;
    color: #ffb0b6;
    padding: 4px 8px;
}

QLabel#status-dim,
QLabel#task-status-dim {
    background-color: #20252b;
    border: 1px solid #3d4651;
    border-radius: 6px;
    color: #aab4bf;
    padding: 4px 8px;
}
"""
