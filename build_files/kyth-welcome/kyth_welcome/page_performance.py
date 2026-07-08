import glob
import os
import json
import sqlite3
import subprocess
from datetime import datetime

# __KYTH_GENERATED_IMPORTS__
from .qt import (  # noqa: E501
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QTimer, QVBoxLayout, QWidget, Qt,
)
from .widgets import (  # noqa: E501
    Page, _make_card,
)

# ── Page: Performance ─────────────────────────────────────────────────────────
class PerformancePage(Page):
    def __init__(self):
        super().__init__()
        self._page_header(
            "Gaming",
            "Scheduler & Performance",
            "kyth-sched auto-switches between scx_lavd (gaming) and scx_bpfland (desktop) "
            "based on active game detection. Session history is captured by kyth-telem "
            "from MangoHud logs.",
        )

        # ── Scheduler status ───────────────────────────────────────────────────
        sched_card, sched_layout = _make_card()
        sched_title = QLabel("Active Scheduler")
        sched_title.setObjectName("card-title")
        sched_layout.addWidget(sched_title)

        status_row = QHBoxLayout()
        status_row.setSpacing(24)

        state_col = QVBoxLayout()
        state_col.setSpacing(8)

        def _sr(label: str) -> tuple[QHBoxLayout, QLabel]:
            row = QHBoxLayout()
            row.setSpacing(8)
            k = QLabel(label)
            k.setObjectName("prop-key")
            k.setMinimumWidth(96)
            row.addWidget(k)
            v = QLabel("—")
            v.setObjectName("prop-val")
            row.addWidget(v, 1)
            return row, v

        prof_row,   self._perf_profile_lbl  = _sr("Profile:")
        sched_row,  self._perf_sched_lbl    = _sr("Scheduler:")
        gaming_row, self._perf_gaming_lbl   = _sr("Gaming:")
        for row in (prof_row, sched_row, gaming_row):
            state_col.addLayout(row)
        status_row.addLayout(state_col, 1)

        ctrl_col = QVBoxLayout()
        ctrl_col.setSpacing(8)
        ctrl_col.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._perf_sched_combo = QComboBox()
        self._perf_sched_combo.setMinimumWidth(160)
        self._populate_sched_combo()
        ctrl_col.addWidget(self._perf_sched_combo)

        apply_btn = QPushButton("Apply Manually")
        apply_btn.setToolTip("Switch scheduler immediately (bypasses auto-switching)")
        apply_btn.clicked.connect(self._apply_scheduler)
        ctrl_col.addWidget(apply_btn)

        self._perf_auto_toggle = QCheckBox("Auto-switch (kyth-sched)")
        self._perf_auto_toggle.setObjectName("card-copy")
        self._perf_auto_toggle.stateChanged.connect(self._toggle_sched_daemon)
        ctrl_col.addWidget(self._perf_auto_toggle)

        status_row.addLayout(ctrl_col)
        sched_layout.addLayout(status_row)
        self._add(sched_card)

        # ── Session history ────────────────────────────────────────────────────
        self._divider()
        hist_head = QLabel("Session History")
        hist_head.setObjectName("h2-heading")
        self._add(hist_head)
        hist_sub = QLabel(
            "Per-session averages captured by kyth-telem from MangoHud CSV logs. "
            "Launch games with MangoHud enabled — data appears here after each session ends."
        )
        hist_sub.setObjectName("caption-text")
        hist_sub.setWordWrap(True)
        self._add(hist_sub)

        sess_card, sess_card_layout = _make_card()
        self._perf_no_data_lbl = QLabel(
            "No sessions yet. Launch a game with MangoHud enabled — "
            "data will appear here automatically."
        )
        self._perf_no_data_lbl.setObjectName("card-copy")
        self._perf_no_data_lbl.setWordWrap(True)
        sess_card_layout.addWidget(self._perf_no_data_lbl)
        self._perf_sessions_layout = QVBoxLayout()
        self._perf_sessions_layout.setSpacing(2)
        sess_card_layout.addLayout(self._perf_sessions_layout)
        self._add(sess_card)

        self._stretch()

        self._perf_timer = QTimer(self)
        self._perf_timer.setInterval(5000)
        self._perf_timer.timeout.connect(self._perf_refresh)
        self._perf_timer.start()
        QTimer.singleShot(150, self._perf_refresh)

    def _populate_sched_combo(self) -> None:
        try:
            r = subprocess.run(
                ["kyth-scx", "list"], capture_output=True, text=True, timeout=5, check=False,
            )
            schedulers = [s.strip() for s in r.stdout.splitlines() if s.strip()]
        except Exception:
            schedulers = []
        if not schedulers:
            try:
                schedulers = sorted(
                    os.path.basename(p) for p in glob.glob("/usr/bin/scx_*")
                    if os.path.isfile(p) and not p.endswith("scx_loader")
                )
            except Exception:
                pass
        self._perf_sched_combo.clear()
        self._perf_sched_combo.addItems(schedulers or ["scx_lavd", "scx_bpfland", "scx_rusty"])

    def _perf_refresh(self) -> None:
        self._refresh_sched_status()
        self._refresh_session_history()

    def _refresh_sched_status(self) -> None:
        uid = os.getuid()
        status_file = os.path.join(
            os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{uid}"),
            "kyth-sched-status.json",
        )
        status = {}
        try:
            with open(status_file) as f:
                status = json.load(f)
        except Exception:
            pass

        profile = status.get("profile", "")
        sched   = status.get("scheduler", "")
        gaming  = status.get("gaming_active", False)
        override = status.get("manual_override", False)

        prof_text = profile.title() if profile else "—"
        if override:
            prof_text += " (manual)"
        self._perf_profile_lbl.setText(prof_text)
        self._perf_sched_lbl.setText(sched or "—")

        if gaming:
            self._perf_gaming_lbl.setText("Active")
            self._perf_gaming_lbl.setStyleSheet("color: #4caf50; font-weight: 700;")
        else:
            self._perf_gaming_lbl.setText("Not detected")
            self._perf_gaming_lbl.setStyleSheet("color: #b0bccf;")

        try:
            r = subprocess.run(
                ["systemctl", "--user", "is-active", "kyth-sched.service"],
                capture_output=True, text=True, timeout=3, check=False,
            )
            self._perf_auto_toggle.blockSignals(True)
            self._perf_auto_toggle.setChecked(r.stdout.strip() == "active")
            self._perf_auto_toggle.blockSignals(False)
        except Exception:
            pass

    def _refresh_session_history(self) -> None:
        db_path = os.path.join(
            os.path.expanduser("~"), ".local", "share", "kyth", "telemetry.db",
        )
        if not os.path.exists(db_path):
            return
        try:
            conn = sqlite3.connect(db_path, timeout=3)
            rows = conn.execute(
                "SELECT game_name, started_at, duration_s, avg_fps, p1_low_fps, "
                "stutter_count, scheduler FROM sessions ORDER BY started_at DESC LIMIT 15"
            ).fetchall()
            conn.close()
        except Exception:
            return

        # Clear old rows
        while self._perf_sessions_layout.count():
            item = self._perf_sessions_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not rows:
            self._perf_no_data_lbl.show()
            return

        self._perf_no_data_lbl.hide()
        for (game, started, duration, avg_fps, p1, stutters, sched) in rows:
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 3, 0, 3)
            row_l.setSpacing(16)

            name_lbl = QLabel(game or "Unknown")
            name_lbl.setObjectName("prop-val")
            name_lbl.setMinimumWidth(160)
            row_l.addWidget(name_lbl)

            date_str = ""
            if started:
                try:
                    date_str = datetime.fromtimestamp(started).strftime("%b %d %H:%M")
                except Exception:
                    pass
            date_lbl = QLabel(date_str or "—")
            date_lbl.setObjectName("prop-val-dim")
            date_lbl.setMinimumWidth(88)
            row_l.addWidget(date_lbl)

            dur_str = "—"
            if duration:
                m, s = divmod(int(duration), 60)
                dur_str = f"{m}m {s:02d}s"
            dur_lbl = QLabel(dur_str)
            dur_lbl.setObjectName("prop-val")
            dur_lbl.setMinimumWidth(72)
            row_l.addWidget(dur_lbl)

            fps_text = f"{avg_fps:.0f} / {p1:.0f} 1%" if avg_fps else "—"
            fps_lbl = QLabel(fps_text)
            fps_lbl.setObjectName("prop-val-blue")
            fps_lbl.setMinimumWidth(120)
            row_l.addWidget(fps_lbl)

            sc = stutters or 0
            stutter_lbl = QLabel(f"{sc} stutter{'s' if sc != 1 else ''}")
            stutter_lbl.setObjectName("prop-val-red" if sc > 20 else "prop-val")
            stutter_lbl.setMinimumWidth(88)
            row_l.addWidget(stutter_lbl)

            sched_lbl = QLabel(sched or "")
            sched_lbl.setObjectName("prop-val-dim")
            row_l.addWidget(sched_lbl, 1)

            self._perf_sessions_layout.addWidget(row_w)

    def _apply_scheduler(self) -> None:
        sched = self._perf_sched_combo.currentText()
        if not sched:
            return
        try:
            subprocess.Popen(
                ["sudo", "-n", "/usr/bin/kyth-scx", "set", sched],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _toggle_sched_daemon(self, state: int) -> None:
        cmd = "start" if state else "stop"
        try:
            subprocess.Popen(
                ["systemctl", "--user", cmd, "kyth-sched.service"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
