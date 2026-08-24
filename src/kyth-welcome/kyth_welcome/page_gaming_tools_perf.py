# __KYTH_GENERATED_IMPORTS__
from .core_base import restyle
from .services.gaming import scx_scheduler_command
from .services.runtime import Worker, guard_disposed, finish_worker, guard_disposed
from .qt import QHBoxLayout, QLabel, QComboBox, QProgressBar, QPushButton, Qt
from .widgets import CollapsibleLogPanel, _copy_text, _launch_opt_label, _launch_opt_value, _make_card


class _PerfTuningMixin:
    """MangoHud, Gamescope, sched-ext, and the per-game launch-option profile builder."""

    def _build_advanced_kernel_card(self):
        """Advanced — Kernel switch hidden here. Fedora default (Secure Boot zero-touch), Cachy opt-in via MOK."""
        from .services.bootc import REGISTRY, branch_display_name, current_branch, current_kernel_flavor, image_tag_for_kernel
        from .services.diagnostics import command_stdout
        from .services.privileged import bootc_action
        from .core_base import run_worker
        from .services.process import with_idle_inhibit

        card, layout = _make_card("card-accent-warn")
        title = QLabel("Advanced — Kernel")
        title.setObjectName("card-title-warn")
        layout.addWidget(title)
        desc = QLabel(
            "Fedora is the default — Secure Boot works with no extra steps. "
            "CachyOS is an opt-in gaming kernel (BORE). Switching downloads a different image, needs one reboot and, if Secure Boot is on, a one-time blue MokManager enroll (<b>ujust enroll-secureboot</b>)."
        )
        desc.setObjectName("card-copy")
        desc.setWordWrap(True)
        desc.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(desc)
        cur = QLabel()
        cur.setObjectName("card-copy")
        cur.setWordWrap(True)
        layout.addWidget(cur)

        status = QLabel()
        status.setObjectName("card-copy")
        status.setWordWrap(True)
        status.hide()
        layout.addWidget(status)

        def do_switch(flavor: str):
            tag = image_tag_for_kernel(flavor)
            ref = f"{REGISTRY}:{tag}"
            status.setText(f"Switching to {flavor} ({ref}) — downloading… Reboot to apply. For Cachy + Secure Boot: ujust secureboot-status")
            status.show()
            run_worker(
                self,
                with_idle_inhibit(bootc_action("switch", ref).command(), "KythOS is switching kernel image"),
                session_inhibit_reason="KythOS is switching kernel image",
                on_line=lambda t: status.setText(t.strip()[-120:]),
                on_done=lambda ok: status.setText("Done — reboot to apply. If Secure Boot: ujust enroll-secureboot before reboot." if ok else "Switch failed — see log."),
            )

        row = QHBoxLayout()
        btns: dict[str, QPushButton] = {}
        for flavor in ("fedora", "cachy"):
            btn = QPushButton("Use Fedora" if flavor == "fedora" else "Switch to CachyOS")
            btn.clicked.connect(lambda _=False, f=flavor: do_switch(f))
            row.addWidget(btn)
            btns[flavor] = btn
        layout.addLayout(row)
        hint = QLabel("Rollback stays available from Updates page and boot menu if a custom kernel misbehaves.")
        hint.setObjectName("card-copy")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        def refresh():
            flavor = current_kernel_flavor()
            kernel = command_stdout(["uname", "-r"]) or "unknown"
            channel = branch_display_name(current_branch())
            names = {"fedora": "Fedora", "cachy": "CachyOS"}
            cur.setText(f"Current: {names.get(flavor, flavor)} · {kernel} · {channel}")
            for k, b in btns.items():
                if k == flavor:
                    b.setText("Current")
                    b.setEnabled(False)
                else:
                    b.setText("Use Fedora" if k == "fedora" else "Switch to CachyOS")
                    b.setEnabled(True)
                restyle(b)

        self._advanced_kernel_refresh = refresh
        refresh()
        self._add(card)

    def _build_overlays_bulk_card(self):
        """One-tap MangoHud + Gamescope + vkBasalt — what Windows switcher expects as 'overlays'."""
        card, layout = _make_card()
        top = QHBoxLayout()
        title = QLabel("Overlays — MangoHud + Gamescope + vkBasalt")
        title.setObjectName("card-title")
        top.addWidget(title)
        top.addStretch()
        # Per-tool badges updated by page_gaming._refresh_status via apply_install_badge
        from .qt import QLabel as _QLabel  # local to keep import order stable
        self._bulk_mh_badge = _QLabel()
        self._bulk_mh_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self._bulk_mh_badge)
        self._bulk_gs_badge = _QLabel()
        self._bulk_gs_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self._bulk_gs_badge)
        self._bulk_vk_badge = _QLabel()
        self._bulk_vk_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self._bulk_vk_badge)
        layout.addLayout(top)
        desc = QLabel(
            "One-tap performance overlays: MangoHud (FPS/OSD), Gamescope (compositor + FSR), "
            "and vkBasalt (contrast/sharpen). Toggle MangoHud in-game with Right Shift + F12."
        )
        desc.setObjectName("card-copy")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        # Combined launch options — copy as a single line (Windows muscle memory: one checkbox)
        for label, opt in (
            ("MangoHud + vkBasalt:", "MANGOHUD=1 ENABLE_VKBASALT=1 %command%"),
            ("All three via Gamescope:", "MANGOHUD=1 ENABLE_VKBASALT=1 kyth-gamescope quality -- %command%"),
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
            layout.addLayout(row)
        hint = QLabel("Installed badges reflect /usr/bin/mangohud, /usr/bin/gamescope, and libvkbasalt.so — no background scan.")
        hint.setObjectName("card-copy")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._add(card)

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
            "Pick a common goal and copy the Steam launch option. Per-game HDR "
            "and latency are saved to ~/.config/kyth/gaming-per-game.toml so "
            "launches stay lean (no global LD_PRELOAD) and survive reboots."
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

        # R4: per-game persistence — save HDR + latency choice to gaming-per-game.toml
        per_game_row = QHBoxLayout()
        per_game_row.setSpacing(8)
        from .widgets import ToggleSwitch

        per_game_hdr_label = QLabel("HDR per game (KYTH_HDR=1)")
        per_game_hdr_label.setObjectName("card-copy")
        per_game_row.addWidget(per_game_hdr_label)
        self._per_game_hdr_check = ToggleSwitch()
        self._per_game_hdr_check.setToolTip("Save HDR=1 for this app so kyth-gamescope adds --hdr-enabled on next launch")
        per_game_row.addWidget(self._per_game_hdr_check)
        self._per_game_save_btn = QPushButton("Save per-game")
        self._per_game_save_btn.setToolTip("Save profile + HDR to ~/.config/kyth/gaming-per-game.toml")
        self._per_game_save_btn.clicked.connect(self._save_per_game_profile)
        per_game_row.addWidget(self._per_game_save_btn)
        self._per_game_status = QLabel("")
        self._per_game_status.setObjectName("card-copy")
        per_game_row.addWidget(self._per_game_status, 1)
        per_game_row.addStretch()
        profile_layout.addLayout(per_game_row)
        hint = QLabel("Saved per-game — launch env is KYTH_HDR + LOW_LATENCY_LAYER/MANGOHUD, no global layer.")
        hint.setObjectName("card-copy")
        hint.setWordWrap(True)
        profile_layout.addWidget(hint)

        self._profile_goal_combo.currentIndexChanged.connect(self._update_profile_builder)
        self._profile_fps_combo.currentIndexChanged.connect(self._update_profile_builder)
        self._per_game_hdr_check.toggled.connect(self._update_profile_builder)
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
        self._scx_log_panel = CollapsibleLogPanel(max_height=100)
        scx_layout.addWidget(self._scx_log_panel)
        self._scx_worker = None
        self._add(scx_card)

    def _update_profile_builder(self):
        if not hasattr(self, "_profile_launch_value"):
            return
        goal = self._profile_goal_combo.currentData() or "quality"
        fps = self._profile_fps_combo.currentData() or ""
        hdr = bool(getattr(self, "_per_game_hdr_check", None) and self._per_game_hdr_check.isChecked())
        hdr_prefix = "KYTH_HDR=1 " if hdr else ""
        fps_arg = f" --fps {fps}" if fps else ""
        launch_options = {
            "quality": f"{hdr_prefix}kyth-gamescope quality{fps_arg} -- %command%",
            "hdr": f"KYTH_HDR=1 kyth-gamescope hdr{fps_arg} -- %command%",
            "sharp": f"{hdr_prefix}kyth-gamescope sharp --fsr{fps_arg} -- %command%",
            "latency": f"{hdr_prefix}game-performance --profile gaming -- kyth-gamescope latency{fps_arg} -- %command%",
            "troubleshoot": "PROTON_LOG=1 PROTON_NO_NTSYNC=1 %command%",
        }
        self._profile_launch_value.setText(launch_options.get(goal, launch_options["quality"]))

    def _save_per_game_profile(self):
        try:
            from kyth_shared.gaming_per_game import set_profile_for_appid

            goal = self._profile_goal_combo.currentData() or "quality"
            hdr = bool(self._per_game_hdr_check.isChecked())
            # Use a placeholder appid for the builder; per-game page will call with real appid
            appid = getattr(self, "_current_per_game_appid", "builder-default")
            set_profile_for_appid(appid, profile=goal, hdr=hdr)
            self._per_game_status.setText(f"Saved {goal} hdr={hdr} for {appid}")
            self._per_game_status.setObjectName("status-ok")
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
            self._per_game_status.setText(f"Save failed: {exc}")
            self._per_game_status.setObjectName("status-err")
        from .core_base import restyle

        restyle(self._per_game_status)

    def _set_scx_scheduler(self, scheduler: str):
        if self._scx_worker and self._scx_worker.isRunning():
            return

        cmd = scx_scheduler_command(scheduler)

        self._scx_log_panel.reset(f"→ {' '.join(cmd)}\n")
        self._scx_progress.show()
        self._scx_status_lbl.setText(f"Setting scheduler: {scheduler}…")
        self._scx_status_lbl.setObjectName("subheading")
        restyle(self._scx_status_lbl)

        self._scx_worker = Worker(cmd)
        self._scx_worker.line.connect(guard_disposed(self._scx_log_panel.append))
        self._scx_worker.done.connect(guard_disposed(self._on_scx_done))
        self._scx_worker.start()

    def _on_scx_done(self, code: int):
        self._scx_progress.hide()
        finish_worker(self, attr="_scx_worker")
        if code == 0:
            self._scx_status_lbl.setText("sched-ext updated.")
            self._scx_status_lbl.setObjectName("status-ok")
            self._scx_log_panel.append("\nDone.")
        else:
            self._scx_status_lbl.setText(f"sched-ext update failed (exit {code}).")
            self._scx_status_lbl.setObjectName("status-err")
        restyle(self._scx_status_lbl)
        self._refresh_status()