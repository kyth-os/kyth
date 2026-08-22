"""Kyth Pulse shell — icon rail, mode switch, home orb, destination tiles."""
from ..ui_tokens import (
    KYTH_BLUE,
    KYTH_BLUE_GLOW,
    KYTH_BLUE_LIGHT,
    KYTH_HAIRLINE,
    KYTH_HAIRLINE_LIGHT,
    KYTH_SURFACE,
    KYTH_SURFACE_OVERLAY,
    KYTH_SURFACE_RAISED,
    KYTH_TEXT,
    KYTH_TEXT_FAINT,
    KYTH_TEXT_MUTED,
    STATUS_OK,
    STATUS_WARN,
)

PULSE_QSS = f"""
/* ── Pulse icon rail ─────────────────────────────────────────────────────── */
QWidget#pulse-rail {{
    background: #0a0e14;
    border-right: 1px solid {KYTH_HAIRLINE};
}}

QLabel#pulse-rail-logo {{
    color: {KYTH_BLUE_LIGHT};
    font-size: 20px;
    font-weight: 800;
    letter-spacing: -0.6px;
    padding: 0;
}}

QPushButton#pulse-rail-btn,
QPushButton#pulse-rail-btn-active,
QPushButton#pulse-rail-btn-badge {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 12px;
    padding: 0;
    color: {KYTH_TEXT_MUTED};
    font-size: 16px;
    font-weight: 700;
}}

QPushButton#pulse-rail-btn:hover {{
    background: {KYTH_SURFACE};
    color: {KYTH_TEXT};
    border-color: {KYTH_HAIRLINE};
}}

QPushButton#pulse-rail-btn:focus,
QPushButton#pulse-rail-btn-active:focus,
QPushButton#pulse-rail-btn-badge:focus {{
    border: 1px solid {KYTH_BLUE};
}}

QPushButton#pulse-rail-btn-active {{
    background: {KYTH_BLUE_GLOW};
    color: {KYTH_TEXT};
    border: 1px solid rgba(56, 189, 248, 92);
}}

QPushButton#pulse-rail-btn-badge {{
    color: {KYTH_BLUE};
    background: rgba(56, 189, 248, 31);
    border: 1px solid rgba(56, 189, 248, 92);
}}

/* ── Mode switch ─────────────────────────────────────────────────────────── */
QPushButton#mode-switch,
QPushButton#mode-switch-active {{
    background: transparent;
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 8px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
    color: {KYTH_TEXT_MUTED};
}}

QPushButton#mode-switch:hover {{
    background: {KYTH_SURFACE_RAISED};
    color: {KYTH_TEXT};
}}

QPushButton#mode-switch-active {{
    background: {KYTH_SURFACE_RAISED};
    border-color: {KYTH_BLUE};
    color: {KYTH_TEXT};
    font-weight: 700;
}}

/* ── Pulse home ──────────────────────────────────────────────────────────── */
QLabel#pulse-greeting {{
    font-size: 28px;
    font-weight: 800;
    letter-spacing: -0.6px;
    color: {KYTH_TEXT};
}}

QLabel#pulse-subhead {{
    font-size: 13px;
    color: {KYTH_TEXT_MUTED};
}}

QFrame#pulse-orb-ok,
QFrame#pulse-orb-warn {{
    border-radius: 66px;
    min-width: 132px;
    max-width: 132px;
    min-height: 132px;
    max-height: 132px;
}}

QFrame#pulse-orb-ok {{
    background: rgba(16, 185, 129, 18);
    border: 3px solid {STATUS_OK};
}}

QFrame#pulse-orb-warn {{
    background: rgba(245, 158, 11, 18);
    border: 3px solid {STATUS_WARN};
}}

QLabel#pulse-orb-label {{
    font-size: 15px;
    font-weight: 800;
    letter-spacing: 0.8px;
    color: {KYTH_TEXT};
}}

QLabel#pulse-orb-caption {{
    font-size: 11px;
    color: {KYTH_TEXT_MUTED};
}}

QFrame#pulse-action {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 16px;
}}

QLabel#pulse-action-title {{
    font-size: 18px;
    font-weight: 750;
    letter-spacing: -0.3px;
    color: {KYTH_TEXT};
}}

QLabel#pulse-action-body {{
    font-size: 13px;
    color: {KYTH_TEXT_MUTED};
}}

QFrame#pulse-facts {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 12px;
}}

QLabel#pulse-fact-key {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.8px;
    color: {KYTH_TEXT_FAINT};
}}

QLabel#pulse-fact-val {{
    font-size: 13px;
    font-weight: 600;
    color: {KYTH_TEXT};
}}

QPushButton#pulse-dest-tile {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-left: 3px solid transparent;
    border-radius: 14px;
    padding: 16px 18px;
    text-align: left;
    color: {KYTH_TEXT};
    font-size: 14px;
    font-weight: 600;
}}

QPushButton#pulse-dest-tile:hover {{
    background: {KYTH_SURFACE_RAISED};
    border-color: {KYTH_HAIRLINE_LIGHT};
    border-left-color: {KYTH_BLUE};
    color: {KYTH_BLUE_LIGHT};
}}

QFrame#pulse-hub-card {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 14px;
}}

QPushButton#pulse-hub-link {{
    background: transparent;
    border: none;
    color: {KYTH_BLUE_LIGHT};
    font-size: 12px;
    font-weight: 600;
    padding: 4px 8px;
}}

QPushButton#pulse-hub-link:hover {{
    color: {KYTH_TEXT};
    background: {KYTH_SURFACE_OVERLAY};
    border-radius: 6px;
}}

QPushButton#pulse-chip {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 12px;
    padding: 12px 14px;
    text-align: left;
    color: {KYTH_TEXT};
    font-size: 13px;
    font-weight: 600;
}}

QPushButton#pulse-chip:hover {{
    background: {KYTH_SURFACE_RAISED};
    border-color: {KYTH_BLUE};
    color: {KYTH_BLUE_LIGHT};
}}

QPushButton#pulse-step,
QPushButton#pulse-step-active {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 10px;
    padding: 10px 12px;
    color: {KYTH_TEXT_MUTED};
    font-size: 13px;
    font-weight: 600;
}}

QPushButton#pulse-step-active {{
    border-color: {KYTH_BLUE};
    color: {KYTH_TEXT};
    background: {KYTH_BLUE_GLOW};
}}

QLabel#pulse-timeline-title {{
    font-size: 12px;
    font-weight: 700;
    color: {KYTH_TEXT};
    min-width: 88px;
}}

QLabel#pulse-timeline-body {{
    font-size: 13px;
    color: {KYTH_TEXT_MUTED};
}}
"""
