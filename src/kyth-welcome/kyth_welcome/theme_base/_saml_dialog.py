"""VPN SAML browser dialog QSS — deliberately its own bespoke dark "browser
chrome" palette (not KYTH_* tokens) so the embedded auth page reads as a
neutral browser window rather than a KythOS-branded surface.
"""

SAML_DIALOG_QSS = """
QDialog#saml-dialog {
    background: #111418;
}
QFrame#saml-header {
    background: #171b21;
    border: 1px solid #2a313a;
    border-radius: 8px;
}
QLabel#saml-title {
    color: #f1f5f9;
    font-size: 16px;
    font-weight: 700;
}
QLabel#saml-info {
    color: #aeb8c5;
    font-size: 12px;
}
QFrame#saml-browser-frame {
    background: #ffffff;
    border: 1px solid #303844;
    border-radius: 8px;
}
QLabel#saml-status {
    color: #9fb0c2;
    font-size: 12px;
}
QPushButton#saml-cancel {
    background: #232a33;
    border: 1px solid #3a4452;
    border-radius: 6px;
    color: #edf2f7;
    padding: 7px 18px;
}
QPushButton#saml-cancel:hover {
    background: #2d3642;
}
QPushButton#saml-cancel:pressed {
    background: #1d232b;
}
"""
