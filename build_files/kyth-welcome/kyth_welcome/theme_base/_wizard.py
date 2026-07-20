"""Wizard QSS styles.

Kyth Theme wizard shell: a left-hand step rail instead of the old top-dot
progress track, and its own card/chip language (``wiz-*`` object names) kept
deliberately separate from the Hub's ``card``/``card-accent-*`` selectors so
restyling the Hub later doesn't ripple into the wizard, and vice versa. Colors
come from ui_tokens.KYTH_* — see that module for the palette rationale.
"""
from ..ui_tokens import (
    KYTH_BLUE, KYTH_BLUE_DIM, KYTH_GROUND, KYTH_HAIRLINE, KYTH_RADIUS,
    KYTH_SURFACE, KYTH_SURFACE_RAISED, KYTH_TEXT, KYTH_TEXT_FAINT,
    KYTH_TEXT_MUTED, STATUS_ERROR, STATUS_OK, STATUS_WARN,
)

WIZARD_QSS = f"""
/* ── Wizard shell ────────────────────────────────────────────────────────── */
QMainWindow#wiz-window,
QWidget#wiz-window {{
    background: {KYTH_GROUND};
}}

QWidget#wiz-rail {{
    background: rgba(255, 255, 255, 6);
    border-right: 1px solid {KYTH_HAIRLINE};
}}

QLabel#wiz-rail-brand {{
    font-size: 15px;
    font-weight: 800;
    color: {KYTH_TEXT};
    letter-spacing: 0.2px;
}}

QLabel#wiz-rail-title {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.2px;
    color: {KYTH_TEXT_FAINT};
}}

/* Step numeral badge — QLabel, fixed size, circular */
QLabel#wiz-step-num-upcoming {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 13px;
    color: {KYTH_TEXT_FAINT};
    font-size: 12px;
    font-weight: 800;
}}

QLabel#wiz-step-num-active {{
    background: {KYTH_BLUE};
    border: 1px solid {KYTH_BLUE};
    border-radius: 13px;
    color: #06101f;
    font-size: 12px;
    font-weight: 800;
}}

QLabel#wiz-step-num-done {{
    background: transparent;
    border: 1px solid {STATUS_OK};
    border-radius: 13px;
    color: {STATUS_OK};
    font-size: 13px;
    font-weight: 800;
}}

QLabel#wiz-step-label-upcoming {{
    font-size: 13px;
    color: {KYTH_TEXT_FAINT};
}}

QLabel#wiz-step-label-active {{
    font-size: 13px;
    font-weight: 700;
    color: {KYTH_TEXT};
}}

QLabel#wiz-step-label-done {{
    font-size: 13px;
    color: {KYTH_TEXT_MUTED};
}}

QFrame#wiz-rail-rule-upcoming {{
    background: {KYTH_HAIRLINE};
    border: none;
    max-width: 1px;
}}

QFrame#wiz-rail-rule-done {{
    background: {KYTH_BLUE_DIM};
    border: none;
    max-width: 1px;
}}

/* ── Body ────────────────────────────────────────────────────────────────── */
QWidget#wiz-body {{
    background: {KYTH_GROUND};
}}

QLabel#wiz-pill {{
    font-size: 10.5px;
    font-weight: 800;
    letter-spacing: 0.8px;
    color: {KYTH_BLUE};
    background: rgba(91, 140, 255, 30);
    border: 1px solid rgba(91, 140, 255, 90);
    border-radius: 999px;
    padding: 5px 11px;
}}

QLabel#wiz-heading {{
    font-size: 30px;
    font-weight: 800;
    color: {KYTH_TEXT};
    letter-spacing: 0.1px;
}}

QLabel#wiz-subheading {{
    font-size: 14px;
    color: {KYTH_TEXT_MUTED};
    line-height: 1.5;
}}

/* ── Profile cards (clickable QWidget, "checked" dynamic property) ───────── */
QWidget#wiz-profile-card {{
    background: {KYTH_SURFACE_RAISED};
    border: 1.5px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS}px;
}}

QWidget#wiz-profile-card[checked="true"] {{
    border-color: {KYTH_BLUE};
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(91, 140, 255, 36), stop:1 rgba(91, 140, 255, 10));
}}

QWidget#wiz-profile-card[checked="true"] QLabel#wiz-card-title {{
    color: {KYTH_BLUE};
}}

/* ── Wizard cards (decoupled from the Hub's card/card-accent-* rules) ─────── */
QFrame#wiz-card {{
    background: {KYTH_SURFACE_RAISED};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: {KYTH_RADIUS}px;
}}

QFrame#wiz-card-warn {{
    background: {KYTH_SURFACE_RAISED};
    border: 1px solid {KYTH_HAIRLINE};
    border-left: 3px solid {STATUS_WARN};
    border-radius: {KYTH_RADIUS}px;
}}

QFrame#wiz-card-ok {{
    background: {KYTH_SURFACE_RAISED};
    border: 1px solid {KYTH_HAIRLINE};
    border-left: 3px solid {STATUS_OK};
    border-radius: {KYTH_RADIUS}px;
}}

QLabel#wiz-card-title {{
    font-size: 13.5px;
    font-weight: 700;
    color: {KYTH_TEXT};
}}

QLabel#wiz-card-copy {{
    font-size: 12.5px;
    color: {KYTH_TEXT_MUTED};
    line-height: 1.5;
}}

/* ── Stat tiles (kernel / Proton-CachyOS / scheduler) ───────────────────── */
QFrame#wiz-stat {{
    background: transparent;
    border: none;
}}

QLabel#wiz-stat-label {{
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.8px;
    color: {KYTH_TEXT_FAINT};
}}

QLabel#wiz-stat-value {{
    font-size: 14px;
    font-weight: 700;
    color: {KYTH_TEXT};
}}

QFrame#wiz-stat-sep {{
    background: {KYTH_HAIRLINE};
    border: none;
    max-width: 1px;
}}

/* ── Finish-step status rows ─────────────────────────────────────────────── */
QFrame#wiz-status-row {{
    background: transparent;
    border-top: 1px solid {KYTH_HAIRLINE};
}}

QLabel#wiz-chip-done {{
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.3px;
    color: {STATUS_OK};
    background: rgba(52, 211, 153, 26);
    border-radius: 999px;
    padding: 3px 9px;
}}

QLabel#wiz-chip-skipped {{
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.3px;
    color: {STATUS_WARN};
    background: rgba(245, 165, 36, 26);
    border-radius: 999px;
    padding: 3px 9px;
}}

QLabel#wiz-chip-pending {{
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.3px;
    color: {KYTH_TEXT_FAINT};
    background: rgba(255, 255, 255, 12);
    border-radius: 999px;
    padding: 3px 9px;
}}

QLabel#wiz-chip-error {{
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.3px;
    color: {STATUS_ERROR};
    background: rgba(247, 118, 142, 26);
    border-radius: 999px;
    padding: 3px 9px;
}}

/* ── Footer ──────────────────────────────────────────────────────────────── */
QWidget#wiz-footer {{
    background: {KYTH_SURFACE};
    border-top: 1px solid {KYTH_HAIRLINE};
}}

QLabel#wiz-footer-hint {{
    color: {KYTH_TEXT_FAINT};
    font-size: 12px;
}}

QLabel#finish-title {{
    font-size: 26px;
    font-weight: 800;
    color: {KYTH_TEXT};
}}

QLabel#finish-subtitle {{
    font-size: 14px;
    color: {KYTH_TEXT_MUTED};
    line-height: 1.6;
}}
"""
