"""Page header — breathing room + progressive typography.

Header is no longer a flat ground strip; it's transparent over the page
canvas with a soft hairline rule, so the content feels like it floats. Title
is tighter tracking (-0.4px) like Windows Settings, eyebrow is smaller and
lighter so it doesn't compete.
"""
from ..ui_tokens import KYTH_BLUE_LIGHT, KYTH_HAIRLINE, KYTH_TEXT, KYTH_TEXT_MUTED

HEADER_QSS = f"""
/* ── Page header band ────────────────────────────────────────────────────── */
QWidget#page-header {{
    background: transparent;
    border-bottom: 1px solid {KYTH_HAIRLINE};
}}

QLabel#page-eyebrow,
QLabel#eyebrow {{
    color: {KYTH_BLUE_LIGHT};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
    padding: 0;
}}

QLabel#page-title,
QLabel#heading {{
    font-size: 26px;
    font-weight: 800;
    letter-spacing: -0.4px;
    color: {KYTH_TEXT};
}}

QLabel#subheading,
QLabel#page-subtitle,
QLabel#wizard-desc {{
    font-size: 13px;
    color: {KYTH_TEXT_MUTED};
    line-height: 1.4;
}}

QLabel#section-heading {{
    font-size: 16px;
    font-weight: 700;
    letter-spacing: -0.2px;
    color: {KYTH_TEXT};
}}
"""
