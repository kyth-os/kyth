# __KYTH_GENERATED_IMPORTS__
from .core_base import restyle
from .services.runtime import DataWorker
from .services.sched import (
    apply_scheduler,
    is_sched_daemon_active,
    list_schedulers,
    read_sched_status,
    set_sched_daemon_enabled,
)
from .qt import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QTimer, QVBoxLayout, QWidget, Qt, single_shot,
)
from .widgets import (
    Page, _make_card,
)

# ── Page: Performance ─────────────────────────────────────────────────────────
class PerformancePage(Page):
    def __init__(self):
        super().__init__()
        self._telemetry_worker = None
        self._sched_daemon_worker = None
        self._scheduler_list_worker = None
        self._page_header(
            "Gaming",
            "Scheduler & Performance",
            "kyth-sched enables scx_rusty for gaming and restores the kernel scheduler for desktop use "
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

        # One-click Gaming Preset (5/5) — stage cachyos + scx bore + mangohud together
        preset_btn = QPushButton("Apply Gaming Preset")
        preset_btn.setObjectName("primary")
        preset_btn.setToolTip("Stage cachyos kernel + scx bore + MangoHud for next boot — one tap for Gaming Rig")
        preset_btn.clicked.connect(self._apply_gaming_preset)
        ctrl_col.addWidget(preset_btn)

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
        single_shot(self, 150, self._perf_refresh)
        single_shot(self, 0, self._refresh_scheduler_list)

    def _apply_gaming_preset(self) -> None:
        """One tap: cachyos kernel + scx bore + auto-switch on — mirrors wizard/steps_machine."""
        try:
            self._perf_sched_combo.setCurrentText("scx_bore")
            self._apply_scheduler()
            self._perf_auto_toggle.setChecked(True)
        except Exception:
            pass
        from .services.launch import popen
        popen(["notify-send", "Gaming Preset staged — reboot to apply cachyos + scx bore"])

    def _populate_sched_combo(self) -> None:
        # list_schedulers() runs `kyth-scx list`; PerformancePage is built
        # lazily on first visit, but this still must not block that first
        # visit on a subprocess call. Seed the combo with the same
        # fallback list_schedulers() itself returns when the probe fails,
        # then _refresh_scheduler_list() (kicked off from __init__ via
        # single_shot) replaces it with the real list once resolved.
        self._perf_sched_combo.clear()
        self._perf_sched_combo.addItem("scx_rusty")

    def _refresh_scheduler_list(self) -> None:
        if self._scheduler_list_worker is not None:
            return
        worker = DataWorker("scheduler-list", list_schedulers)
        self._scheduler_list_worker = worker
        worker.result.connect(lambda _key, schedulers: self._apply_scheduler_list(schedulers))
        worker.failed.connect(lambda _key, _message: None)
        worker.finished.connect(lambda: setattr(self, "_scheduler_list_worker", None))
        worker.start()

    def _apply_scheduler_list(self, schedulers: list[str]) -> None:
        current = self._perf_sched_combo.currentText()
        self._perf_sched_combo.clear()
        self._perf_sched_combo.addItems(schedulers)
        idx = self._perf_sched_combo.findText(current)
        self._perf_sched_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _perf_refresh(self) -> None:
        self._refresh_sched_status()
        self._refresh_session_history()

    def _refresh_sched_status(self) -> None:
        status = read_sched_status()
        profile = status.get("profile", "")
        sched = status.get("scheduler", "")
        gaming = status.get("gaming_active", False)
        override = status.get("manual_override", False)

        prof_text = profile.title() if profile else "—"
        if override:
            prof_text += " (manual)"
        self._perf_profile_lbl.setText(prof_text)
        self._perf_sched_lbl.setText(sched or "—")

        if gaming:
            self._perf_gaming_lbl.setText("Active")
            self._perf_gaming_lbl.setObjectName("prop-val-green")
        else:
            self._perf_gaming_lbl.setText("Not detected")
            self._perf_gaming_lbl.setObjectName("card-copy")
        restyle(self._perf_gaming_lbl)

        self._refresh_sched_daemon_state()

    def _refresh_sched_daemon_state(self) -> None:
        # is_sched_daemon_active() shells out to `systemctl --user
        # is-active`. This page's 5s heartbeat timer calls
        # _refresh_sched_status() (and therefore this) for as long as the
        # page stays open, so it must run off the GUI thread — a call made
        # while a previous one is still in flight is a no-op, and the next
        # tick retries.
        if self._sched_daemon_worker is not None:
            return
        worker = DataWorker("sched-daemon-active", is_sched_daemon_active)
        self._sched_daemon_worker = worker
        worker.result.connect(lambda _key, active: self._apply_sched_daemon_state(bool(active)))
        worker.failed.connect(lambda _key, _message: None)
        worker.finished.connect(lambda: setattr(self, "_sched_daemon_worker", None))
        worker.start()

    def _apply_sched_daemon_state(self, active: bool) -> None:
        self._perf_auto_toggle.blockSignals(True)
        self._perf_auto_toggle.setChecked(active)
        self._perf_auto_toggle.blockSignals(False)

    def _refresh_session_history(self) -> None:
        if hasattr(self, "_telemetry_worker") and self._telemetry_worker is not None:
            if self._telemetry_worker.isRunning():
                return

        from .services.workers import TelemetryWorker
        self._telemetry_worker = TelemetryWorker(limit=15, parent=self)
        self._telemetry_worker.loaded.connect(self._on_sessions_loaded)
        self._telemetry_worker.start()

    def _on_sessions_loaded(self, rows: list) -> None:
        while self._perf_sessions_layout.count():
            item = self._perf_sessions_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not rows:
            self._perf_no_data_lbl.show()
            return

        self._perf_no_data_lbl.hide()
        for session in rows:
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 3, 0, 3)
            row_l.setSpacing(16)

            name_lbl = QLabel(session.game_name)
            name_lbl.setObjectName("prop-val")
            name_lbl.setMinimumWidth(160)
            row_l.addWidget(name_lbl)

            date_lbl = QLabel(session.date_label)
            date_lbl.setObjectName("prop-val-dim")
            date_lbl.setMinimumWidth(88)
            row_l.addWidget(date_lbl)

            dur_lbl = QLabel(session.duration_label)
            dur_lbl.setObjectName("prop-val")
            dur_lbl.setMinimumWidth(72)
            row_l.addWidget(dur_lbl)

            fps_lbl = QLabel(session.fps_label)
            fps_lbl.setObjectName("prop-val-blue")
            fps_lbl.setMinimumWidth(120)
            row_l.addWidget(fps_lbl)

            sc = session.stutter_count
            stutter_lbl = QLabel(f"{sc} stutter{'s' if sc != 1 else ''}")
            stutter_lbl.setObjectName("prop-val-red" if sc > 20 else "prop-val")
            stutter_lbl.setMinimumWidth(88)
            row_l.addWidget(stutter_lbl)

            sched_lbl = QLabel(session.scheduler)
            sched_lbl.setObjectName("prop-val-dim")
            row_l.addWidget(sched_lbl, 1)

            self._perf_sessions_layout.addWidget(row_w)

    def _apply_scheduler(self) -> None:
        apply_scheduler(self._perf_sched_combo.currentText())

    def _toggle_sched_daemon(self, state: int) -> None:
        set_sched_daemon_enabled(bool(state))
