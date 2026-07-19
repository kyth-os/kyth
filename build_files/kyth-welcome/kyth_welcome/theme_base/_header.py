"""Header QSS styles."""

HEADER_QSS = """
/* ── Page header band ────────────────────────────────────────────────────── */
QWidget#page-header {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e2230, stop:1 #0c0e16);
    border-bottom: 1px solid #1e2230;
}

QLabel#eyebrow {
    color: #8fb8ff;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 0;
}

QLabel#heading {
    font-size: 30px;
    font-weight: 700;
    color: #ffffff;
}

QLabel#subheading {
    font-size: 13px;
    color: #a6a6a6;
    line-height: 1.5;
}

QLabel#section-heading {
    font-size: 16px;
    font-weight: 600;
    color: #ffffff;
}
"""
