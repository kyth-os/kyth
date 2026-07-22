# __KYTH_GENERATED_IMPORTS__
from .core_base import _restyle
from .services.gaming import scx_scheduler_command
from .services.runtime import Worker, _finish_worker
from .qt import QComboBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit, Qt
from .widgets import _copy_text, _launch_opt_label, _launch_opt_value, _make_card, _set_log_panel


class _PerfTuningMixin:
    """MangoHud, Gamescope, sched-ext, and the per-game launch-option profile builder."""

    def _build_mangohud_card(self):
        self._divider()
        mh_card, mh_layout = _make_card()
        mh_top = QHBoxLayout()
        mh_title = QLabel("MangoHud — Performance Overlay")
        mh_title.setObjectName("card-title")
        mh_top.addWidget(mh_title)
        mh_top.addStretch()
        self._mh_badge = QLabel()
        self._mh_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mh_top.addWidget(self._mh_badge)
        mh_layout.addLayout(mh_top)
        mh_desc = QLabel(
            "Shows FPS, frame time, GPU/CPU load and temperature as an in-game overlay. "
            "Toggle on/off at any time with Right Shift + F12."
        )
        mh_desc.setObjectName("card-copy")
        mh_desc.setWordWrap(True)
        mh_layout.addWidget(mh_desc)
        mh_opts = QHBoxLayout()
        mh_opts.setSpacing(10)
        mh_opts.addWidget(_launch_opt_label("Steam launch option:"))
        mh_opts.addWidget(_launch_opt_value("MANGOHUD=1 %command%"))
        mh_copy = QPushButton("Copy")
        mh_copy.clicked.connect(lambda: _copy_text("MANGOHUD=1 %command%"))
        mh_opts.addWidget(mh_copy)
        mh_opts.addStretch()
        mh_layout.addLayout(mh_opts)
        mh_cfg_row = QHBoxLayout()
        mh_cfg_row.setSpacing(10)
        mh_cfg_lbl = QLabel("Config: /etc/MangoHud/MangoHud.conf  ·  override: ~/.config/MangoHud/MangoHud.conf")
        mh_cfg_lbl.setObjectName("card-copy")
        mh_cfg_row.addWidget(mh_cfg_lbl)
        mh_cfg_row.addStretch()
        mh_layout.addLayout(mh_cfg_row)
        self._add(mh_card)

    def _build_gamescope_card(self):
        gs_card, gs_layout = _make_card()
        gs_top = QHBoxLayout()
        gs_title = QLabel("Gamescope — Game Compositor")
        gs_title.setObjectName("card-title")
        gs_top.addWidget(gs_title)
        gs_top.addStretch()
        self._gs_badge = QLabel()
        self._gs_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gs_top.addWidget(self._gs_badge)
        gs_layout.addLayout(gs_top)
        gs_desc = QLabel(
            "Valve's micro-compositor for games: better frame pacing, VRR/adaptive sync, "
            "FSR upscaling, and HDR. Runs the game inside its own compositor so the "
            "desktop is unaffected. Using -e keeps Steam Input and overlay working."
        )
        gs_desc.setObjectName("card-copy")
        gs_desc.setWordWrap(True)
        gs_layout.addWidget(gs_desc)

        for label, opt in (
            ("Quality preset:", "kyth-gamescope quality -- %command%"),
            ("HDR display:", "kyth-gamescope hdr --fps 120 -- %command%"),
            ("Sharp upscaling:", "kyth-gamescope sharp --fsr --nested 1920x1080 --output 2560x1440 -- %command%"),
            ("ujust recipe:", "ujust game-scope quality -- %command%"),
        ):
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(_launch_opt_label(label))
            row.addWidget(_launch_opt_value(opt))
            cp = QPushButton("Copy")
            captured = opt
            cp.clicked.connect(lambda _=False, t=captured: _copy_text(t))
            row.addWidget(cp)
            row.addStretch()
            gs_layout.addLayout(row)
        self._add(gs_card)

    def _build_profile_builder_card(self):
        profile_card, profile_layout = _make_card()
        profile_title = QLabel("Per-Game Profile Builder")
        profile_title.setObjectName("card-title")
        profile_layout.addWidget(profile_title)
        profile_desc = QLabel(
            "Pick a common goal and copy the Steam launch option. Use this before "
            "manual tuning so players get a known-good KythOS baseline first."
        )
        profile_desc.setObjectName("card-copy")
        profile_desc.setWordWrap(True)
        profile_layout.addWidget(profile_desc)

        profile_row = QHBoxLayout()
        profile_row.setSpacing(8)
        self._profile_goal_combo = QComboBox()
        self._profile_goal_combo.addItem("Balanced quality", "quality")
        self._profile_goal_combo.addItem("HDR display", "hdr")
        self._profile_goal_combo.addItem("Sharp upscaling", "sharp")
        self._profile_goal_combo.addItem("Low latency", "latency")
        self._profile_goal_combo.addItem("Troubleshoot launch", "troubleshoot")
        profile_row.addWidget(self._profile_goal_combo)
        self._profile_fps_combo = QComboBox()
        for label, value in (("No FPS cap", ""), ("60 FPS", "60"), ("90 FPS", "90"), ("120 FPS", "120"), ("144 FPS", "144"), ("165 FPS", "165")):
            self._profile_fps_combo.addItem(label, value)
        profile_row.addWidget(self._profile_fps_combo)
        profile_row.addStretch()
        profile_layout.addLayout(profile_row)

        profile_opt_row = QHBoxLayout()
        profile_opt_row.setSpacing(10)
        profile_opt_row.addWidget(_launch_opt_label("Steam launch option:"))
        self._profile_launch_value = _launch_opt_value("")
        profile_opt_row.addWidget(self._profile_launch_value, 1)
        profile_copy = QPushButton("Copy")
        profile_copy.clicked.connect(lambda: _copy_text(self._profile_launch_value.text()))
        profile_opt_row.addWidget(profile_copy)
        profile_layout.addLayout(profile_opt_row)

        self._profile_goal_combo.currentIndexChanged.connect(self._update_profile_builder)
        self._profile_fps_combo.currentIndexChanged.connect(self._update_profile_builder)
        self._add(profile_card)

    def _build_scx_card(self):
        scx_card, scx_layout = _make_card()
        scx_top = QHBoxLayout()
        scx_title = QLabel("sched-ext — CPU Scheduler")
        scx_title.setObjectName("card-title")
        scx_top.addWidget(scx_title)
        scx_top.addStretch()
        self._scx_badge = QLabel()
        self._scx_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scx_top.addWidget(self._scx_badge)
        scx_layout.addLayout(scx_top)
        scx_desc = QLabel(
            "KythOS uses Fedora's packaged scx_rusty scheduler for gaming and "
            "returns to the kernel scheduler for normal desktop work."
        )
        scx_desc.setObjectName("card-copy")
        scx_desc.setWordWrap(True)
        scx_layout.addWidget(scx_desc)
        self._scx_status_lbl = QLabel()
        self._scx_status_lbl.setObjectName("card-copy")
        scx_layout.addWidget(self._scx_status_lbl)
        scx_btns = QHBoxLayout()
        scx_btns.setSpacing(8)
        for label, scheduler in (("Use scx_rusty", "rusty"),):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, sched=scheduler: self._set_scx_scheduler(sched))
            scx_btns.addWidget(btn)
        self._scx_stop_btn = QPushButton("Stop scx")
        self._scx_stop_btn.clicked.connect(lambda _=False: self._set_scx_scheduler("stop"))
        scx_btns.addWidget(self._scx_stop_btn)
        scx_btns.addStretch()
        scx_layout.addLayout(scx_btns)
        self._scx_progress = QProgressBar()
        self._scx_progress.setRange(0, 0)
        self._scx_progress.hide()
        scx_layout.addWidget(self._scx_progress)
        self._scx_log_toggle = QPushButton("Show details")
        self._scx_log_toggle.setCheckable(True)
        self._scx_log_toggle.clicked.connect(lambda checked: _set_log_panel(self._scx_log_toggle, self._scx_log, checked))
        self._scx_log_toggle.hide()
        scx_layout.addWidget(self._scx_log_toggle)
        self._scx_log = QTextEdit()
        self._scx_log.document().setMaximumBlockCount(5000)
        self._scx_log.setReadOnly(True)
        self._scx_log.setMaximumHeight(100)
        self._scx_log.hide()
        scx_layout.addWidget(self._scx_log)
        self._scx_worker = None
        self._add(scx_card)

    def _update_profile_builder(self):
        if not hasattr(self, "_profile_launch_value"):
            return
        goal = self._profile_goal_combo.currentData() or "quality"
        fps = self._profile_fps_combo.currentData() or ""
        fps_arg = f" --fps {fps}" if fps else ""
        launch_options = {
            "quality": f"kyth-gamescope quality{fps_arg} -- %command%",
            "hdr": f"kyth-gamescope hdr{fps_arg} -- %command%",
            "sharp": f"kyth-gamescope sharp --fsr{fps_arg} -- %command%",
            "latency": f"game-performance --profile gaming -- kyth-gamescope latency{fps_arg} -- %command%",
            "troubleshoot": "PROTON_LOG=1 PROTON_NO_NTSYNC=1 %command%",
        }
        self._profile_launch_value.setText(launch_options.get(goal, launch_options["quality"]))

    def _set_scx_scheduler(self, scheduler: str):
        if self._scx_worker and self._scx_worker.isRunning():
            return

        cmd = scx_scheduler_command(scheduler)

        self._scx_log.clear()
        self._scx_log.append(f"→ {' '.join(cmd)}\n")
        self._scx_log_toggle.show()
        _set_log_panel(self._scx_log_toggle, self._scx_log, False)
        self._scx_progress.show()
        self._scx_status_lbl.setText(f"Setting scheduler: {scheduler}…")
        self._scx_status_lbl.setObjectName("subheading")
        _restyle(self._scx_status_lbl)

        self._scx_worker = Worker(cmd)
        self._scx_worker.line.connect(lambda ln: (
            self._scx_log.append(ln),
            self._scx_log.ensureCursorVisible(),
        ))
        self._scx_worker.done.connect(self._on_scx_done)
        self._scx_worker.start()

    def _on_scx_done(self, code: int):
        self._scx_progress.hide()
        _finish_worker(self, attr="_scx_worker")
        if code == 0:
            self._scx_status_lbl.setText("sched-ext updated.")
            self._scx_status_lbl.setObjectName("status-ok")
            self._scx_log.append("\nDone.")
        else:
            self._scx_status_lbl.setText(f"sched-ext update failed (exit {code}).")
            self._scx_status_lbl.setObjectName("status-err")
        _restyle(self._scx_status_lbl)
        self._refresh_status()
