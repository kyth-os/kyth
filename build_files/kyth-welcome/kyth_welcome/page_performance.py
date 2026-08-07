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

        # ── AI Performance daemon (local, 30s TTL) ───────────────────────────
        ai_card, ai_layout = _make_card("card-accent-ok")
        ai_title = QLabel("AI Performance Tuning — offline")
        ai_title.setObjectName("card-title")
        ai_layout.addWidget(ai_title)
        ai_desc = QLabel(
            "Kyth AI watches gaming/cgroup pressure and power, picks scx + sysctl + GPU via local qwen2.5-coder (or deterministic fallback), and auto-reverts in 30s if p95 worsens. No cloud."
        )
        ai_desc.setObjectName("card-copy")
        ai_desc.setWordWrap(True)
        ai_layout.addWidget(ai_desc)
        ai_row = QHBoxLayout()
        ai_row.setSpacing(12)
        self._ai_status_lbl = QLabel("AI: checking…")
        self._ai_status_lbl.setObjectName("prop-val")
        ai_row.addWidget(self._ai_status_lbl, 1)
        self._ai_toggle = QCheckBox("Enable AI tuning (kyth-ai-perfd)")
        self._ai_toggle.setChecked(True)
        self._ai_toggle.setToolTip("Enable the 5s AI daemon — scx_rusty for gaming, bpfland for desktop, lavd for pressure")
        self._ai_toggle.stateChanged.connect(self._toggle_ai_perf)
        ai_row.addWidget(self._ai_toggle)
        ai_apply = QPushButton("Apply AI policy now")
        ai_apply.clicked.connect(self._apply_ai_now)
        ai_row.addWidget(ai_apply)
        ai_layout.addLayout(ai_row)
        self._add(ai_card)

                # ── Clean perf — opt-in, zero cost when off (46-50) ───────────────────
        clean_card, clean_layout = _make_card()
        clean_title = QLabel("Clean Perf — zero cost when off")
        clean_title.setObjectName("card-title")
        clean_layout.addWidget(clean_title)
        clean_desc = QLabel("Kargs/I/O/Net/UKSmd/Journal + THP/Mimalloc/IRQ/Btrfs/Trim — off by default, TOML in /etc/kyth, revertible.")
        clean_desc.setObjectName("card-copy")
        clean_desc.setWordWrap(True)
        clean_layout.addWidget(clean_desc)
        clean_row = QHBoxLayout()
        clean_row.setSpacing(8)
        self._clean_status = QLabel("Clean perf: checking…")
        self._clean_status.setObjectName("prop-val-dim")
        clean_row.addWidget(self._clean_status, 1)
        btn_kargs = QPushButton("Kargs")
        btn_kargs.setToolTip("kargs.toml profile balanced/performance/gaming (mitigations=off only in gaming)")
        btn_kargs.clicked.connect(self._clean_kargs_status)
        clean_row.addWidget(btn_kargs)
        btn_io = QPushButton("I/O")
        btn_io.clicked.connect(lambda: self._run_clean("io"))
        clean_row.addWidget(btn_io)
        btn_net = QPushButton("Net")
        btn_net.clicked.connect(lambda: self._run_clean("net"))
        clean_row.addWidget(btn_net)
        btn_uksmd = QPushButton("UKSmd")
        btn_uksmd.clicked.connect(lambda: self._run_clean("uksmd"))
        clean_row.addWidget(btn_uksmd)
        btn_journal = QPushButton("Journal")
        btn_journal.clicked.connect(lambda: self._run_clean("journal"))
        clean_row.addWidget(btn_journal)
        clean_layout.addLayout(clean_row)
        # row 2: 51-55
        clean_row2 = QHBoxLayout()
        clean_row2.setSpacing(8)
        clean_row2.addWidget(QLabel(""), 1)
        btn_thp = QPushButton("THP")
        btn_thp.clicked.connect(lambda: self._run_clean("thp"))
        clean_row2.addWidget(btn_thp)
        btn_mimalloc = QPushButton("Mimalloc")
        btn_mimalloc.clicked.connect(lambda: self._run_clean("mimalloc"))
        clean_row2.addWidget(btn_mimalloc)
        btn_irq = QPushButton("IRQ")
        btn_irq.clicked.connect(lambda: self._run_clean("irq"))
        clean_row2.addWidget(btn_irq)
        btn_btrfs = QPushButton("Btrfs")
        btn_btrfs.clicked.connect(lambda: self._run_clean("btrfs"))
        clean_row2.addWidget(btn_btrfs)
        btn_trim = QPushButton("Trim")
        btn_trim.clicked.connect(lambda: self._run_clean("trim"))
        clean_row2.addWidget(btn_trim)
        clean_layout.addLayout(clean_row2)
        # row 3: 56-60
        clean_row3 = QHBoxLayout()
        clean_row3.setSpacing(8)
        clean_row3.addWidget(QLabel(""), 1)
        btn_ananicy = QPushButton("Ananicy")
        btn_ananicy.clicked.connect(lambda: self._run_clean("ananicy"))
        clean_row3.addWidget(btn_ananicy)
        btn_zswap = QPushButton("Zswap")
        btn_zswap.clicked.connect(lambda: self._run_clean("zswap"))
        clean_row3.addWidget(btn_zswap)
        btn_gpu = QPushButton("GPU")
        btn_gpu.clicked.connect(lambda: self._run_clean("gpu"))
        clean_row3.addWidget(btn_gpu)
        btn_sched = QPushButton("Sched")
        btn_sched.clicked.connect(lambda: self._run_clean("sched"))
        clean_row3.addWidget(btn_sched)
        btn_readahead = QPushButton("Readahead")
        btn_readahead.clicked.connect(lambda: self._run_clean("readahead"))
        clean_row3.addWidget(btn_readahead)
        clean_layout.addLayout(clean_row3)
        # row 4: 61-65 master + wine/kwin/pipewire/btrfs-autotune
        clean_row4 = QHBoxLayout()
        clean_row4.setSpacing(8)
        btn_master = QPushButton("MASTER Gaming")
        btn_master.setObjectName("primary")
        btn_master.setToolTip("gaming-performance.toml one toggle for 46-60 (kargs/io/thp/irq/btrfs/trim/ananicy/zswap/sched/net)")
        btn_master.clicked.connect(lambda: self._run_clean("master"))
        clean_row4.addWidget(btn_master)
        btn_wine = QPushButton("WineSync")
        btn_wine.clicked.connect(lambda: self._run_clean("wine"))
        clean_row4.addWidget(btn_wine)
        btn_kwin = QPushButton("KWin")
        btn_kwin.clicked.connect(lambda: self._run_clean("kwin"))
        clean_row4.addWidget(btn_kwin)
        btn_pipe = QPushButton("PipeWG")
        btn_pipe.clicked.connect(lambda: self._run_clean("pipewire"))
        clean_row4.addWidget(btn_pipe)
        btn_bauto = QPushButton("BtrfsAuto")
        btn_bauto.clicked.connect(lambda: self._run_clean("btrfsauto"))
        clean_row4.addWidget(btn_bauto)
        clean_layout.addLayout(clean_row4)
        self._add(clean_card)

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

    def _toggle_ai_perf(self, state: int) -> None:
        from kyth_shared.commands import run

        action = "enable" if state else "disable"
        run(["systemctl", "--user", action, "--now", "kyth-ai-perfd.service"], capture_output=True, timeout=10)
        self._ai_status_lbl.setText(f"AI: {'enabled' if state else 'disabled'}")
        restyle(self._ai_status_lbl)

    def _apply_ai_now(self) -> None:
        from kyth_shared.ai_perf_daemon import apply_policy, choose_policy, collect_sample

        try:
            sample = collect_sample()
            policy = choose_policy(sample)
            ok = apply_policy(policy)
            self._ai_status_lbl.setText(f"AI: {policy.reason} → {policy.scx} ({'ok' if ok else 'failed'})")
            restyle(self._ai_status_lbl)
        except Exception as exc:
            self._ai_status_lbl.setText(f"AI: failed — {exc}")
            restyle(self._ai_status_lbl)

    def _clean_kargs_status(self) -> None:
        try:
            from kyth_shared.kargs_preset import load_kargs, kargs_drift
            c = load_kargs()
            d = kargs_drift()
            self._clean_status.setText(f"kargs {c['profile']} missing={d['missing'] or '∅'}")
            restyle(self._clean_status)
        except Exception as exc:
            self._clean_status.setText(f"kargs failed — {exc}")
            restyle(self._clean_status)

    def _run_clean(self, which: str) -> None:
        try:
            if which == "io":
                from kyth_shared.io_tune import load_io_tune, io_status
                c = load_io_tune()
                self._clean_status.setText(f"io {c['profile']} rule={io_status()}")
            elif which == "net":
                from kyth_shared.net_latency import load_net_latency, net_latency_status
                c = load_net_latency()
                self._clean_status.setText(f"net enabled={c['enabled']} active={net_latency_status()}")
            elif which == "uksmd":
                from kyth_shared.uksmd_preset import load_uksmd, uksmd_suggested
                c = load_uksmd()
                self._clean_status.setText(f"uksmd enabled={c['enabled']} suggested={uksmd_suggested()}")
            elif which == "journal":
                from kyth_shared.journal_tune import load_journal, journal_status
                c = load_journal()
                self._clean_status.setText(f"journal perf={c['perf']} active={journal_status()}")
            elif which == "thp":
                from kyth_shared.thp_tune import load_thp, thp_status
                c = load_thp()
                self._clean_status.setText(f"thp {c['profile']} active={thp_status()}")
            elif which == "mimalloc":
                from kyth_shared.mimalloc_preset import load_mimalloc, mimalloc_status
                c = load_mimalloc()
                self._clean_status.setText(f"mimalloc {c['enabled']} {mimalloc_status()}")
            elif which == "irq":
                from kyth_shared.irq_tune import load_irq, irq_status
                c = load_irq()
                self._clean_status.setText(f"irq {c['profile']} active={irq_status()}")
            elif which == "btrfs":
                from kyth_shared.btrfs_perf import load_btrfs_perf, btrfs_perf_status
                c = load_btrfs_perf()
                self._clean_status.setText(f"btrfs {c['profile']} active={btrfs_perf_status()}")
            elif which == "trim":
                from kyth_shared.trim_preset import load_trim, trim_status
                c = load_trim()
                self._clean_status.setText(f"trim {c['profile']} active={trim_status()}")
            elif which == "ananicy":
                from kyth_shared.ananicy_preset import load_ananicy, ananicy_status
                c = load_ananicy()
                self._clean_status.setText(f"ananicy {c['profile']} active={ananicy_status()}")
            elif which == "zswap":
                from kyth_shared.zswap_preset import load_zswap, zswap_status
                c = load_zswap()
                self._clean_status.setText(f"zswap {c['profile']} active={zswap_status()}")
            elif which == "gpu":
                from kyth_shared.gpu_power import load_gpu_power
                c = load_gpu_power()
                self._clean_status.setText(f"gpu {c['profile']} dpm={c['dpm']}")
            elif which == "sched":
                from kyth_shared.sched_latency import load_sched_latency, sched_latency_status
                c = load_sched_latency()
                self._clean_status.setText(f"sched {c['profile']} active={sched_latency_status()}")
            elif which == "readahead":
                from kyth_shared.readahead_preset import load_readahead
                c = load_readahead()
                self._clean_status.setText(f"readahead {c['enabled']} {c['size_mb']}MB")
            elif which == "master":
                from kyth_shared.gaming_master import load_master
                c = load_master()
                self._clean_status.setText(f"master {c['profile']} 46-60")
            elif which == "wine":
                from kyth_shared.wine_sync import load_wine_sync, wine_sync_status, probe_wine_sync
                c = load_wine_sync()
                self._clean_status.setText(f"wine {c['mode']} probe={probe_wine_sync()} env={wine_sync_status()}")
            elif which == "kwin":
                from kyth_shared.kwin_latency import load_kwin_latency, kwin_latency_status
                c = load_kwin_latency()
                self._clean_status.setText(f"kwin {c['profile']} active={kwin_latency_status()}")
            elif which == "pipewire":
                from kyth_shared.pipewire_gaming import load_pipewire_gaming, pipewire_gaming_status
                c = load_pipewire_gaming()
                self._clean_status.setText(f"pipewire {c['profile']} q={c['quantum']} active={pipewire_gaming_status()}")
            elif which == "btrfsauto":
                from kyth_shared.btrfs_autotune import load_btrfs_autotune
                c = load_btrfs_autotune()
                self._clean_status.setText(f"btrfs-auto {c['enabled']} thr={c['threshold']}")
            restyle(self._clean_status)
        except Exception as exc:
            self._clean_status.setText(f"{which} failed — {exc}")
            restyle(self._clean_status)
