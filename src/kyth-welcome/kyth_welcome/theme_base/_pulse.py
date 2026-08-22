"""Kyth Pulse shell — labeled rail, mode switch, home orb, destination tiles."""
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
/* ── Pulse labeled rail ──────────────────────────────────────────────────── */
QWidget#pulse-rail {{
    background: #070a10;
    border-right: 1px solid {KYTH_HAIRLINE};
}}

QLabel#pulse-rail-logo {{
    color: {KYTH_BLUE_LIGHT};
    font-size: 22px;
    font-weight: 800;
    letter-spacing: -0.8px;
    padding: 0;
}}

QLabel#pulse-rail-wordmark {{
    color: {KYTH_TEXT_FAINT};
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 2.4px;
    padding: 0 0 4px 0;
}}

QPushButton#pulse-rail-btn,
QPushButton#pulse-rail-btn-active,
QPushButton#pulse-rail-btn-badge {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 14px;
    padding: 0;
    color: {KYTH_TEXT_MUTED};
}}

QPushButton#pulse-rail-btn QLabel#pulse-rail-glyph,
QPushButton#pulse-rail-btn-active QLabel#pulse-rail-glyph,
QPushButton#pulse-rail-btn-badge QLabel#pulse-rail-glyph {{
    color: {KYTH_TEXT_MUTED};
    font-size: 18px;
    font-weight: 700;
    background: transparent;
}}

QPushButton#pulse-rail-btn QLabel#pulse-rail-caption,
QPushButton#pulse-rail-btn-active QLabel#pulse-rail-caption,
QPushButton#pulse-rail-btn-badge QLabel#pulse-rail-caption {{
    color: {KYTH_TEXT_FAINT};
    font-size: 11px;
    font-weight: 650;
    letter-spacing: 0.2px;
    background: transparent;
}}

QPushButton#pulse-rail-btn:hover {{
    background: {KYTH_SURFACE};
    border-color: {KYTH_HAIRLINE};
}}

QPushButton#pulse-rail-btn:hover QLabel#pulse-rail-glyph,
QPushButton#pulse-rail-btn:hover QLabel#pulse-rail-caption {{
    color: {KYTH_TEXT};
}}

QPushButton#pulse-rail-btn:focus,
QPushButton#pulse-rail-btn-active:focus,
QPushButton#pulse-rail-btn-badge:focus {{
    border: 1px solid {KYTH_BLUE};
}}

QPushButton#pulse-rail-btn-active {{
    background: {KYTH_BLUE_GLOW};
    border: 1px solid rgba(56, 189, 248, 92);
}}

QPushButton#pulse-rail-btn-active QLabel#pulse-rail-glyph,
QPushButton#pulse-rail-btn-active QLabel#pulse-rail-caption {{
    color: {KYTH_TEXT};
}}

QPushButton#pulse-rail-btn-badge {{
    background: rgba(245, 158, 11, 28);
    border: 1px solid {STATUS_WARN};
}}

QPushButton#pulse-rail-btn-badge QLabel#pulse-rail-glyph,
QPushButton#pulse-rail-btn-badge QLabel#pulse-rail-caption {{
    color: {STATUS_WARN};
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
    font-size: 32px;
    font-weight: 800;
    letter-spacing: -0.8px;
    color: {KYTH_TEXT};
}}

QLabel#pulse-subhead {{
    font-size: 14px;
    color: {KYTH_TEXT_MUTED};
}}

QFrame#pulse-orb-ok,
QFrame#pulse-orb-warn {{
    border-radius: 72px;
    min-width: 144px;
    max-width: 144px;
    min-height: 144px;
    max-height: 144px;
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
    border-radius: 18px;
}}

QLabel#pulse-action-title {{
    font-size: 20px;
    font-weight: 750;
    letter-spacing: -0.4px;
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
    border-radius: 16px;
    padding: 0;
    text-align: left;
    color: {KYTH_TEXT};
}}

QPushButton#pulse-dest-tile:hover {{
    background: {KYTH_SURFACE_RAISED};
    border-color: {KYTH_HAIRLINE_LIGHT};
    border-left-color: {KYTH_BLUE};
}}

QLabel#pulse-dest-glyph {{
    color: {KYTH_BLUE_LIGHT};
    font-size: 20px;
    font-weight: 700;
    background: transparent;
}}

QLabel#pulse-dest-title {{
    color: {KYTH_TEXT};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: -0.2px;
    background: transparent;
}}

QLabel#pulse-dest-copy {{
    color: {KYTH_TEXT_MUTED};
    font-size: 12px;
    background: transparent;
}}

QPushButton#pulse-dest-tile:hover QLabel#pulse-dest-title {{
    color: {KYTH_BLUE_LIGHT};
}}

QLabel#pulse-hub-glyph {{
    color: {KYTH_BLUE_LIGHT};
    font-size: 22px;
    font-weight: 700;
    padding-right: 8px;
}}

QWidget#pulse-hub-tabs QFrame#segmented-tab-row {{
    background: transparent;
    border: none;
    border-radius: 0;
}}

QWidget#pulse-hub-tabs QPushButton#segmented-tab {{
    border-radius: 999px;
    padding: 8px 16px;
}}

QFrame#pulse-hub-card {{
    background: {KYTH_SURFACE};
    border: 1px solid {KYTH_HAIRLINE};
    border-radius: 16px;
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
    border-radius: 14px;
    padding: 14px 16px;
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
    border-radius: 12px;
    padding: 12px 14px;
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
