"""Wizard QSS styles."""

WIZARD_QSS = """
/* ── Wizard ──────────────────────────────────────────────────────────────── */
QWidget#wizard-header {
    background: #12141f;
    border-bottom: 1px solid #1e2230;
}

QWidget#wizard-footer {
    background: #12141f;
    border-top: 1px solid #1e2230;
}

QLabel#wizard-footer-hint {
    color: #a6a6a6;
    font-size: 12px;
}

QLabel#step-dot-active {
    background: #8fb8ff;
    border-radius: 5px;
}

QLabel#step-dot-done {
    background: #4f8cff;
    border-radius: 5px;
}

QLabel#step-dot-inactive {
    background: #2e324c;
    border-radius: 5px;
}

QLabel#wizard-progress-step {
    font-size: 11px;
    font-weight: 400;
    color: #8a8a8a;
}

QLabel#wizard-progress-step-active {
    font-size: 11px;
    font-weight: 600;
    color: #ffffff;
}

QLabel#wizard-progress-step-done {
    font-size: 11px;
    font-weight: 400;
    color: #8fb8ff;
}

QWidget#wizard-hero {
    background: #12141f;
}

QLabel#wizard-logo {
    font-size: 48px;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: -1px;
}

QLabel#wizard-tagline {
    font-size: 16px;
    color: #8fb8ff;
    font-weight: 600;
}

QLabel#wizard-desc {
    font-size: 13px;
    color: #a6a6a6;
    line-height: 1.6;
}

QLabel#finish-title {
    font-size: 26px;
    font-weight: 700;
    color: #ffffff;
}

QLabel#finish-subtitle {
    font-size: 14px;
    color: #a6a6a6;
    line-height: 1.6;
}
"""
