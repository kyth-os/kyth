"""Status QSS styles."""

STATUS_QSS = """
/* ── Status labels ───────────────────────────────────────────────────────── */
QLabel#status-ok {
    color: #10b981;
    font-weight: 600;
}

QLabel#status-warn {
    color: #f59e0b;
    font-weight: 600;
}

QLabel#status-err {
    color: #ff99a4;
    font-weight: 600;
}

QLabel#status-dim {
    color: #8a8a8a;
}

QLabel#task-status-idle,
QLabel#task-status-running,
QLabel#task-status-ok,
QLabel#task-status-warn,
QLabel#task-status-err {
    border-radius: 5px;
    padding: 8px 10px;
    font-weight: 600;
}

QLabel#task-status-idle {
    background: #151722;
    color: #a6a6a6;
    border: 1px solid #26293a;
}

QLabel#task-status-running {
    background: #1c253d;
    color: #c2d9ff;
    border: 1px solid #3d5d8a;
}

QLabel#task-status-ok {
    background: #0f2018;
    color: #34d399;
    border: 1px solid #10b981;
}

QLabel#task-status-warn {
    background: #22160a;
    color: #fbbf24;
    border: 1px solid #f59e0b;
}

QLabel#task-status-err {
    background: #271416;
    color: #ff99a4;
    border: 1px solid #5e3338;
}

QFrame#action-row {
    background: transparent;
    border: none;
}

QFrame#command-result-panel {
    background: transparent;
    border: none;
}

QFrame#empty-state {
    background: #151722;
    border: 1px dashed #2e324c;
    border-radius: 6px;
}

QLabel#empty-state-title {
    color: #ffffff;
    font-size: 14px;
    font-weight: 700;
}

QLabel#empty-state-copy {
    color: #a6a6a6;
    line-height: 1.5;
}

QFrame#flow-step {
    background: #151722;
    border: 1px solid #26293a;
    border-radius: 6px;
}

QLabel#flow-step-num {
    background: #1c253d;
    color: #c2d9ff;
    border: 1px solid #3d5d8a;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 700;
}

QLabel#flow-step-title {
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
}

QLabel#flow-step-copy {
    color: #a6a6a6;
    line-height: 1.45;
}
"""
