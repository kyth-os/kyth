"""Shared styling roles for the cloud-storage setup wizard."""

CLOUD_QSS = r"""
QDialog#cloud-wizard {
    background: #1e1e1e;
}
QWidget#cloud-wizard-header {
    background: #1b1b1c;
    border-bottom: 1px solid #2e2e2e;
}
QWidget#cloud-wizard-footer {
    background: #181818;
    border-top: 1px solid #2b2b2b;
}
QLabel#cloud-wizard-title {
    color: #ffffff;
    font-size: 16px;
    font-weight: 700;
}
QLabel#cloud-step-label,
QLabel#cloud-hint {
    color: #858585;
    font-size: 12px;
}
QLabel#cloud-page-heading {
    color: #ffffff;
    font-size: 17px;
    font-weight: 700;
}
QLabel#cloud-done-heading {
    color: #4dbb6f;
    font-size: 22px;
    font-weight: 700;
}
QLabel#cloud-field-label {
    color: #cccccc;
    font-weight: 600;
}
QLabel#cloud-command-label {
    color: #cccccc;
    font-size: 13px;
    font-weight: 600;
}
QFrame#cloud-divider {
    background: #26293a;
    border: none;
    max-height: 1px;
}
QPushButton#cloud-service {
    background: #151722;
    border: 1px solid #26293a;
    border-radius: 8px;
    text-align: left;
}
QPushButton#cloud-service:checked {
    background: rgba(79, 140, 255, 0.18);
    border: 2px solid #4f8cff;
    border-radius: 6px;
}
QLabel#cloud-service-name {
    background: transparent;
    border: none;
    font-size: 14px;
    font-weight: 700;
}
QLabel#cloud-service-copy {
    background: transparent;
    border: none;
    color: #a6a6a6;
    font-size: 12px;
}
"""
