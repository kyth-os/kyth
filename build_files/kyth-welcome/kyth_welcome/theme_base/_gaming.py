"""Gaming QSS styles."""

GAMING_QSS = """
/* ── Gaming readiness panel ──────────────────────────────────────────────── */
QLabel#ready-score {
    color: #10b981;
    font-size: 28px;
    font-weight: 700;
}

QLabel#ready-score-warn {
    color: #f59e0b;
    font-size: 28px;
    font-weight: 700;
}

QLabel#ready-score-err {
    color: #ff99a4;
    font-size: 28px;
    font-weight: 700;
}

QLabel#ready-row-ok,
QLabel#ready-row-warn,
QLabel#ready-row-err,
QLabel#ready-row-dim {
    border-radius: 5px;
    padding: 8px 10px;
    font-weight: 600;
}

QLabel#ready-row-ok {
    background: #0f2018;
    color: #34d399;
    border: 1px solid #10b981;
}

QLabel#ready-row-warn {
    background: #22160a;
    color: #fbbf24;
    border: 1px solid #f59e0b;
}

QLabel#ready-row-err {
    background: #271416;
    color: #ff99a4;
    border: 1px solid #5e3338;
}

QLabel#ready-row-dim {
    background: #151722;
    color: #a6a6a6;
    border: 1px solid #26293a;
}
"""
