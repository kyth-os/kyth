import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

# __KYTH_GENERATED_IMPORTS__
from .core_base import _cancel_worker, _restyle
from .services.gaming import (  # noqa: E501
    GAMING_TOOLS, heroic_epic_launcher_command, lutris_installer_command, opticscaler_deploy_command,
    scx_scheduler_command
)
from .services.software import Worker, _finish_worker, _install_flatpak_inline, _is_flatpak_installed
from .qt import (  # noqa: E501
    QComboBox, QDesktopServices, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QPushButton, QTextEdit, QTimer, QUrl, QVBoxLayout, Qt
)
from .widgets import (
    ActionRow, CommandResultPanel, _copy_text, _launch_opt_label, _launch_opt_value,
    _make_card, _set_log_panel,
)


class _ToolsMixin:
    """Gaming Tools install grid, tuning cards, and Proton-CachyOS management — the GAMING HUB "setup"/"tuning" sections."""

    def _build_gaming_tools_section(self):
        # ── Gaming Tools ──────────────────────────────────────────────────────
        tools_head = QLabel("Gaming Tools")
        tools_head.setObjectName("heading")
        tools_head.setStyleSheet("font-size: 18px; font-weight: 700; color: #ffffff;")
        self._add(tools_head)
        tools_sub = QLabel(
            "Install the launchers and tools you want. "
            "Bottles is the easiest option for standalone `.exe` and `.msi` installers. "
            "Additional launchers and device tools are available here or via the corresponding ujust recipe."
        )
        tools_sub.setObjectName("card-copy")
        tools_sub.setWordWrap(True)
        self._add(tools_sub)

        self._TOOLS = GAMING_TOOLS

        # Build tiles in a 2-column grid
        self._tool_refs: list[dict] = []
        for i in range(0, len(self._TOOLS), 2):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(16)
            for tool in self._TOOLS[i:i + 2]:
                tile, refs = self._make_tool_tile(tool)
                row_layout.addWidget(tile, 1)
                self._tool_refs.append(refs)
            # Pad the last row if odd number of tools
            if len(self._TOOLS[i:i + 2]) == 1:
                row_layout.addStretch(1)
            self._add_layout(row_layout)

        tuning_card, tuning_layout = _make_card()
        tuning_title = QLabel("Advanced GPU and Capture Tools")
        tuning_title.setObjectName("card-title")
        tuning_layout.addWidget(tuning_title)
        tuning_desc = QLabel(
            "LACT and CoreCtrl cover AMD GPU tuning, while OBS uses the built-in "
            "obs-vkcapture and v4l2loopback support for game capture and virtual camera workflows."
        )
        tuning_desc.setObjectName("card-copy")
        tuning_desc.setWordWrap(True)
        tuning_layout.addWidget(tuning_desc)
        tuning_btns = QHBoxLayout()
        tuning_btns.setSpacing(8)
        lact_btn = QPushButton("Install LACT")
        lact_btn.clicked.connect(lambda _=False, b=lact_btn: _install_flatpak_inline(
            self, b, "io.github.ilya_zlobintsev.LACT", "LACT"))
        tuning_btns.addWidget(lact_btn)
        corectrl_btn = QPushButton("Open CoreCtrl")
        corectrl_btn.clicked.connect(lambda _=False: self._open_corectrl())
        tuning_btns.addWidget(corectrl_btn)
        obs_btn = QPushButton("Install OBS")
        obs_btn.clicked.connect(lambda _=False, b=obs_btn: self._install_obs_inline(b))
        tuning_btns.addWidget(obs_btn)
        tuning_btns.addStretch()
        tuning_layout.addLayout(tuning_btns)
        self._add(tuning_card)

        # ── OptiScaler card ──────────────────────────────────────────────────
        opti_card, opti_layout = _make_card()
        opti_title = QLabel("OptiScaler — Universal Upscaling")
        opti_title.setObjectName("card-title")
        opti_layout.addWidget(opti_title)
        opti_desc = QLabel(
            "Enables FSR2/3, XeSS, and DLSS-translation in any DirectX 11/12 game through "
            "Proton's DLL override — including games that ship without upscaling support. "
            "Works on all AMD and Intel GPUs. Deploy to a game folder, then set the Steam "
            "launch option: <code>WINEDLLOVERRIDES=\"nvngx=n,b\" %command%</code>"
        )
        opti_desc.setObjectName("card-copy")
        opti_desc.setWordWrap(True)
        opti_desc.setTextFormat(Qt.TextFormat.RichText)
        opti_layout.addWidget(opti_desc)
        opti_btns = QHBoxLayout()
        opti_btns.setSpacing(8)
        opti_deploy_btn = QPushButton("Deploy to Game Folder…")
        opti_deploy_btn.clicked.connect(
            lambda _=False, b=opti_deploy_btn: self._deploy_opticscaler(b)
        )
        opti_btns.addWidget(opti_deploy_btn)
        self._opti_deploy_btn = opti_deploy_btn
        opti_copy_btn = QPushButton("Copy Launch Option")
        opti_copy_btn.setToolTip('Copies: WINEDLLOVERRIDES="nvngx=n,b" %command%')
        opti_copy_btn.clicked.connect(lambda _=False: self._copy_opticscaler_launch_opt(opti_copy_btn))
        opti_btns.addWidget(opti_copy_btn)
        self._opti_copy_btn = opti_copy_btn
        opti_btns.addStretch()
        opti_layout.addLayout(opti_btns)
        self._opti_status_lbl = QLabel("")
        self._opti_status_lbl.setObjectName("subheading")
        self._opti_status_lbl.hide()
        opti_layout.addWidget(self._opti_status_lbl)
        self._opti_log = QTextEdit()
        self._opti_log.document().setMaximumBlockCount(5000)
        self._opti_log.setReadOnly(True)
        self._opti_log.setMaximumHeight(140)
        self._opti_log.hide()
        opti_layout.addWidget(self._opti_log)
        self._opticscaler_worker: Worker | None = None
        self._add(opti_card)

        streaming_card, streaming_layout = _make_card()
        streaming_top = QHBoxLayout()
        streaming_title = QLabel("Streaming and Discord Readiness")
        streaming_title.setObjectName("card-title")
        streaming_top.addWidget(streaming_title)
        streaming_top.addStretch()
        streaming_refresh = QPushButton("Refresh")
        streaming_refresh.clicked.connect(self._refresh_gaming_dashboard)
        streaming_top.addWidget(streaming_refresh)
        streaming_layout.addLayout(streaming_top)
        streaming_desc = QLabel(
            "PC gamers bring Discord, OBS, capture, microphones, and screen share "
            "expectations with them. This checks the pieces that make that feel normal."
        )
        streaming_desc.setObjectName("card-copy")
        streaming_desc.setWordWrap(True)
        streaming_layout.addWidget(streaming_desc)
        self._streaming_rows_layout = QVBoxLayout()
        self._streaming_rows_layout.setSpacing(8)
        streaming_layout.addLayout(self._streaming_rows_layout)
        streaming_btns = QHBoxLayout()
        streaming_btns.setSpacing(8)
        install_discord = QPushButton("Install Discord")
        install_discord.clicked.connect(lambda _=False, b=install_discord: _install_flatpak_inline(
            self, b, "com.discordapp.Discord", "Discord"))
        streaming_btns.addWidget(install_discord)
        install_obs = QPushButton("Install OBS")
        install_obs.clicked.connect(lambda _=False, b=install_obs: self._install_obs_inline(b))
        streaming_btns.addWidget(install_obs)
        streaming_btns.addStretch()
        streaming_layout.addLayout(streaming_btns)

        # Discord screen share fix card
        discord_fix_card, discord_fix_layout = _make_card()
        discord_fix_title = QLabel("Fix Discord screen share on Wayland")
        discord_fix_title.setObjectName("card-title")
        discord_fix_layout.addWidget(discord_fix_title)
        discord_fix_body = QLabel(
            "Discord screen share is broken by default under Wayland. "
            "This applies the correct Flatpak environment flags and enables PipeWire capture. "
            "Restart Discord after applying. Alternatively, Vesktop (in Gaming Tools above) "
            "has screen share working out of the box."
        )
        discord_fix_body.setObjectName("card-copy")
        discord_fix_body.setWordWrap(True)
        discord_fix_layout.addWidget(discord_fix_body)
        discord_fix_actions = ActionRow("", "idle")
        self._discord_fix_btn = discord_fix_actions.add_button(
            "Fix Discord Screen Share", self._fix_discord_screenshare, primary=True
        )
        discord_fix_actions.finish()
        self._discord_fix_status = discord_fix_actions.status
        self._discord_fix_status.hide()
        discord_fix_layout.addWidget(discord_fix_actions)
        self._discord_fix_result = CommandResultPanel()
        self._discord_fix_result.hide()
        discord_fix_layout.addWidget(self._discord_fix_result)

        # OBS PipeWire setup
        obs_fix_note = QLabel("Fix OBS audio capture (apply PipeWire/Wayland Flatpak permissions)")
        obs_fix_note.setObjectName("card-title")
        obs_fix_note.setStyleSheet("margin-top:8px;")
        discord_fix_layout.addWidget(obs_fix_note)
        obs_fix_body = QLabel(
            "OBS installed from Flathub may not capture audio or display correctly under Wayland. "
            "This grants the required Flatpak socket permissions for PipeWire and Wayland output."
        )
        obs_fix_body.setObjectName("card-copy")
        obs_fix_body.setWordWrap(True)
        discord_fix_layout.addWidget(obs_fix_body)
        obs_fix_actions = ActionRow("", "idle")
        self._obs_fix_btn = obs_fix_actions.add_button("Fix OBS Audio + Display", self._fix_obs_pipewire)
        obs_fix_actions.finish()
        self._obs_fix_status = obs_fix_actions.status
        self._obs_fix_status.hide()
        discord_fix_layout.addWidget(obs_fix_actions)
        self._obs_fix_result = CommandResultPanel()
        self._obs_fix_result.hide()
        discord_fix_layout.addWidget(self._obs_fix_result)
        self._add(discord_fix_card)

        self._add(streaming_card)

        self._divider()
        launcher_head = QLabel("Launcher setup")
        launcher_head.setObjectName("card-title")
        self._add(launcher_head)
        launcher_sub = QLabel(
            "Heroic is the recommended default for Epic and GOG. "
            "Install Lutris above, then use the buttons below to start Lutris installers for Battle.net, EA App, and Ubisoft Connect."
        )
        launcher_sub.setObjectName("card-copy")
        launcher_sub.setWordWrap(True)
        self._add(launcher_sub)

        launcher_card, launcher_layout = _make_card()
        launcher_note = QLabel(
            "Recommended pairing: Heroic for Epic/GOG/Amazon libraries, Lutris (install above) for Battle.net, EA App, and Ubisoft Connect, and Bottles for standalone .exe / .msi installers."
        )
        launcher_note.setObjectName("card-copy")
        launcher_note.setWordWrap(True)
        launcher_layout.addWidget(launcher_note)

        launcher_btns = QHBoxLayout()
        launcher_btns.setSpacing(8)

        epic_btn = QPushButton("Open Heroic for Epic")
        epic_btn.clicked.connect(lambda _=False: self._open_heroic_for_epic())
        launcher_btns.addWidget(epic_btn)

        battlenet_btn = QPushButton("Install Battle.net")
        battlenet_btn.clicked.connect(
            lambda _=False: self._launch_lutris_installer("battlenet", "Battle.net")
        )
        launcher_btns.addWidget(battlenet_btn)

        ea_btn = QPushButton("Install EA App")
        ea_btn.clicked.connect(
            lambda _=False: self._launch_lutris_installer("lutris:ea-app-standard", "EA App")
        )
        launcher_btns.addWidget(ea_btn)

        ubisoft_btn = QPushButton("Install Ubisoft Connect")
        ubisoft_btn.clicked.connect(
            lambda _=False: self._launch_lutris_installer("lutris:ubisoft-connect-latest", "Ubisoft Connect")
        )
        launcher_btns.addWidget(ubisoft_btn)

        launcher_btns.addStretch()
        launcher_layout.addLayout(launcher_btns)

        # Launcher status / log (used by Open Heroic / Lutris installer buttons)
        self._tool_op_status = QLabel()
        self._tool_op_status.setObjectName("subheading")
        self._tool_op_status.hide()
        launcher_layout.addWidget(self._tool_op_status)
        self._tool_progress = QProgressBar()
        self._tool_progress.setRange(0, 0)
        self._tool_progress.hide()
        launcher_layout.addWidget(self._tool_progress)
        self._tool_cancel_btn = QPushButton("Cancel")
        self._tool_cancel_btn.clicked.connect(self._cancel_launcher_tool_operation)
        self._tool_cancel_btn.hide()
        launcher_layout.addWidget(self._tool_cancel_btn)
        self._tool_log_toggle = QPushButton("Show details")
        self._tool_log_toggle.setCheckable(True)
        self._tool_log_toggle.clicked.connect(lambda checked: _set_log_panel(self._tool_log_toggle, self._tool_log, checked))
        self._tool_log_toggle.hide()
        launcher_layout.addWidget(self._tool_log_toggle)
        self._tool_log = QTextEdit()
        self._tool_log.document().setMaximumBlockCount(5000)
        self._tool_log.setReadOnly(True)
        self._tool_log.setMaximumHeight(120)
        self._tool_log.hide()
        launcher_layout.addWidget(self._tool_log)
        self._add(launcher_card)

        self._tool_worker = None
        self._active_tool_refs = None

        self._active_gaming_section = "tuning"
        self._divider()

        # ── MangoHud ──────────────────────────────────────────────────────────
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

        if not self._wizard_mode:
            # ── Gamescope ─────────────────────────────────────────────────────
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

        # ── Per-game profile builder ─────────────────────────────────────────
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

        if not self._wizard_mode:
            # ── sched-ext ─────────────────────────────────────────────────────
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
                "KythOS uses CachyOS sched-ext support for latency-focused gaming. "
                "lavd is the default all-rounder; rusty and bpfland are useful alternates for testing."
            )
            scx_desc.setObjectName("card-copy")
            scx_desc.setWordWrap(True)
            scx_layout.addWidget(scx_desc)
            self._scx_status_lbl = QLabel()
            self._scx_status_lbl.setObjectName("card-copy")
            scx_layout.addWidget(self._scx_status_lbl)
            scx_btns = QHBoxLayout()
            scx_btns.setSpacing(8)
            for label, scheduler in (
                ("Use lavd", "lavd"),
                ("Use rusty", "rusty"),
                ("Use bpfland", "bpfland"),
            ):
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

        # ── Proton-CachyOS ────────────────────────────────────────────────────
        pc_card, pc_layout = _make_card()
        pc_top = QHBoxLayout()
        pc_title = QLabel("Proton-CachyOS")
        pc_title.setObjectName("card-title")
        pc_top.addWidget(pc_title)
        pc_top.addStretch()
        self._pc_badge = QLabel()
        self._pc_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pc_top.addWidget(self._pc_badge)
        pc_layout.addLayout(pc_top)
        pc_desc = QLabel(
            "CachyOS's Proton build with performance patches, NTSYNC, and Wine "
            "tuning baked in. Installed and kept up to date automatically — no "
            "setup required."
        )
        pc_desc.setObjectName("card-copy")
        pc_desc.setWordWrap(True)
        pc_layout.addWidget(pc_desc)
        self._pc_version_lbl = QLabel()
        self._pc_version_lbl.setObjectName("card-copy")
        pc_layout.addWidget(self._pc_version_lbl)
        pc_btns = QHBoxLayout()
        pc_btns.setSpacing(10)
        self._pc_update_btn = QPushButton("Update Proton-CachyOS")
        self._pc_update_btn.clicked.connect(self._update_proton_cachyos)
        pc_btns.addWidget(self._pc_update_btn)
        pc_btns.addStretch()
        pc_layout.addLayout(pc_btns)
        self._pc_op_status = QLabel()
        self._pc_op_status.hide()
        pc_layout.addWidget(self._pc_op_status)
        self._pc_progress = QProgressBar()
        self._pc_progress.setRange(0, 0)
        self._pc_progress.hide()
        pc_layout.addWidget(self._pc_progress)
        self._pc_log_toggle = QPushButton("Show details")
        self._pc_log_toggle.setCheckable(True)
        self._pc_log_toggle.clicked.connect(lambda checked: _set_log_panel(self._pc_log_toggle, self._pc_log, checked))
        self._pc_log_toggle.hide()
        pc_layout.addWidget(self._pc_log_toggle)
        self._pc_log = QTextEdit()
        self._pc_log.document().setMaximumBlockCount(5000)
        self._pc_log.setReadOnly(True)
        self._pc_log.setMaximumHeight(120)
        self._pc_log.hide()
        pc_layout.addWidget(self._pc_log)
        self._pc_worker = None
        self._add(pc_card)

        if not self._wizard_mode:
            # ── Optional GE-Proton ────────────────────────────────────────────
            ge_card, ge_layout = _make_card()
            ge_top = QHBoxLayout()
            ge_title = QLabel("Optional GE-Proton")
            ge_title.setObjectName("card-title")
            ge_top.addWidget(ge_title)
            ge_top.addStretch()
            self._ge_badge = QLabel()
            self._ge_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ge_top.addWidget(self._ge_badge)
            ge_layout.addLayout(ge_top)
            ge_desc = QLabel(
                "Keep Proton-CachyOS as the default. GE-Proton is worth having as "
                "a second per-game runner for extra game-specific patches, codec "
                "support, and bleeding-edge Wine tweaks not yet in Proton-CachyOS."
            )
            ge_desc.setObjectName("card-copy")
            ge_desc.setWordWrap(True)
            ge_layout.addWidget(ge_desc)
            self._ge_version_lbl = QLabel()
            self._ge_version_lbl.setObjectName("card-copy")
            ge_layout.addWidget(self._ge_version_lbl)
            ge_btns = QHBoxLayout()
            ge_btns.setSpacing(10)
            ge_open = QPushButton("Open ProtonUp-Qt")
            ge_open.clicked.connect(lambda _=False: self._open_protonupqt())
            ge_btns.addWidget(ge_open)
            ge_docs = QPushButton("Open GE-Proton Page")
            ge_docs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/GloriousEggroll/proton-ge-custom")))
            ge_btns.addWidget(ge_docs)
            ge_btns.addStretch()
            ge_layout.addLayout(ge_btns)
            ge_note = QLabel(
                "In ProtonUp-Qt, add a Steam compatibility tool and choose GE-Proton. "
                "Restart Steam, then select it per-game under Properties -> Compatibility."
            )
            ge_note.setObjectName("card-copy")
            ge_note.setWordWrap(True)
            ge_layout.addWidget(ge_note)
            self._add(ge_card)

            # ── vkBasalt ──────────────────────────────────────────────────────
            vk_card, vk_layout = _make_card()
            vk_top = QHBoxLayout()
            vk_title = QLabel("vkBasalt — Vulkan Post-Processing")
            vk_title.setObjectName("card-title")
            vk_top.addWidget(vk_title)
            vk_top.addStretch()
            self._vk_badge = QLabel()
            self._vk_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vk_top.addWidget(self._vk_badge)
            vk_layout.addLayout(vk_top)
            vk_desc = QLabel(
                "Adds post-processing to any Vulkan game: CAS sharpening (default), SMAA, "
                "FXAA, or debanding. Only active when explicitly enabled per-game. "
                "Config: /etc/vkBasalt.conf  ·  toggle key: Home."
            )
            vk_desc.setObjectName("card-copy")
            vk_desc.setWordWrap(True)
            vk_layout.addWidget(vk_desc)
            vk_opts = QHBoxLayout()
            vk_opts.setSpacing(10)
            vk_opts.addWidget(_launch_opt_label("Steam launch option:"))
            vk_opts.addWidget(_launch_opt_value("ENABLE_VKBASALT=1 %command%"))
            vk_copy = QPushButton("Copy")
            vk_copy.clicked.connect(lambda: _copy_text("ENABLE_VKBASALT=1 %command%"))
            vk_opts.addWidget(vk_copy)
            vk_opts.addStretch()
            vk_layout.addLayout(vk_opts)
            self._add(vk_card)

            # ── Combos quick reference ─────────────────────────────────────────
            self._divider()
            combo_head = QLabel("Combining tools")
            combo_head.setObjectName("card-title")
            self._add(combo_head)
            combo_sub = QLabel(
                "These launch options can be stacked freely. "
                "A good all-rounder for most games:"
            )
            combo_sub.setObjectName("card-copy")
            combo_sub.setWordWrap(True)
            self._add(combo_sub)
            combo_txt = QTextEdit()
            combo_txt.setReadOnly(True)
            combo_txt.setMinimumHeight(160)
            combo_txt.setPlainText(
                "# All-rounder: MangoHud overlay + Gamescope compositor\n"
                "kyth-gamescope quality -- %command%\n\n"
                "# Same but with HDR (requires HDR display)\n"
                "kyth-gamescope hdr -- %command%\n\n"
                "# Add CAS sharpening via vkBasalt\n"
                "kyth-gamescope sharp -- %command%\n\n"
                "# GameMode + performance profile (CPU/GPU governors, renice)\n"
                "ujust game-performance -- %command%"
            )
            self._add(combo_txt)

        self._active_gaming_section = "migration"

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

    def _make_tool_tile(self, tool: dict) -> tuple[QFrame, dict]:
        card, layout = _make_card()
        layout.setSpacing(8)

        name_lbl = QLabel(tool["name"])
        name_lbl.setObjectName("card-title")
        layout.addWidget(name_lbl)

        desc_lbl = QLabel(tool["desc"])
        desc_lbl.setObjectName("card-copy")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        install_btn = QPushButton("Install")
        install_btn.clicked.connect(
            lambda _=False, t=tool: self._install_tool(t)
        )
        btn_row.addWidget(install_btn)
        launch_btn = QPushButton("Launch")
        launch_btn.hide()
        launch_btn.clicked.connect(
            lambda _=False, cmd=tool["launch"]: subprocess.Popen(cmd)
        )
        btn_row.addWidget(launch_btn)
        uninstall_btn = QPushButton("Uninstall")
        uninstall_btn.setObjectName("danger")
        uninstall_btn.hide()
        uninstall_btn.clicked.connect(
            lambda _=False, t=tool: self._uninstall_tool(t)
        )
        btn_row.addWidget(uninstall_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.hide()
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        status_lbl = QLabel()
        status_lbl.setObjectName("subheading")
        status_lbl.hide()
        layout.addWidget(status_lbl)

        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.hide()
        layout.addWidget(progress)

        log_toggle = QPushButton("Show details")
        log_toggle.setCheckable(True)
        log_toggle.hide()
        layout.addWidget(log_toggle)

        log = QTextEdit()
        log.setReadOnly(True)
        log.setMaximumHeight(100)
        log.hide()
        layout.addWidget(log)

        log_toggle.clicked.connect(lambda checked, lt=log_toggle, lg=log: _set_log_panel(lt, lg, checked))

        refs = {
            "tool": tool, "install": install_btn, "launch": launch_btn, "uninstall": uninstall_btn,
            "cancel": cancel_btn, "status": status_lbl, "progress": progress,
            "log_toggle": log_toggle, "log": log,
        }
        cancel_btn.clicked.connect(lambda _=False, r=refs: self._cancel_tool_operation(r))
        return card, refs

    def _open_protonupqt(self):
        if _is_flatpak_installed("net.davidotek.pupgui2"):
            subprocess.Popen(["flatpak", "run", "net.davidotek.pupgui2"])
            return
        btn = self.sender()
        if not isinstance(btn, QPushButton):
            btn = QPushButton()

        def _launch_when_done(code: int):
            if code == 0:
                subprocess.Popen(["flatpak", "run", "net.davidotek.pupgui2"])

        _install_flatpak_inline(
            self, btn, "net.davidotek.pupgui2", "ProtonUp-Qt", done_cb=_launch_when_done,
        )

    def _open_corectrl(self):
        if shutil.which("corectrl"):
            subprocess.Popen(["corectrl"])
            return
        QMessageBox.information(
            self,
            "CoreCtrl",
            "CoreCtrl is not installed in this image. Use LACT for AMD GPU tuning, or rebuild with CoreCtrl available in the package repos.",
        )

    def _copy_opticscaler_launch_opt(self, btn: QPushButton):
        _copy_text('WINEDLLOVERRIDES="nvngx=n,b" %command%')
        btn.setText("Copied!")
        QTimer.singleShot(2000, lambda: btn.setText("Copy Launch Option"))

    def _deploy_opticscaler(self, btn: QPushButton):
        if self._opticscaler_worker and self._opticscaler_worker.isRunning():
            return
        game_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Game Directory",
            str(Path.home() / ".local/share/Steam/steamapps/common"),
        )
        if not game_dir:
            return
        btn.setEnabled(False)
        self._opti_log.clear()
        self._opti_log.append(f"→ ujust deploy-opticscaler '{game_dir}'\n")
        self._opti_log.show()
        self._opti_status_lbl.setText("Deploying OptiScaler…")
        self._opti_status_lbl.setObjectName("subheading")
        self._opti_status_lbl.show()
        _restyle(self._opti_status_lbl)
        cmd = opticscaler_deploy_command(game_dir)
        self._opticscaler_worker = Worker(cmd)
        self._opticscaler_worker.line.connect(lambda ln: (
            self._opti_log.append(ln),
            self._opti_log.ensureCursorVisible(),
        ))
        self._opticscaler_worker.done.connect(lambda code: self._on_opticscaler_done(code, btn))
        self._opticscaler_worker.start()

    def _on_opticscaler_done(self, code: int, btn: QPushButton):
        btn.setEnabled(True)
        _finish_worker(self, attr="_opticscaler_worker")
        if code == 0:
            self._opti_status_lbl.setText(
                "Deployed. Set Steam launch option: WINEDLLOVERRIDES=\"nvngx=n,b\" %command%"
            )
            self._opti_status_lbl.setObjectName("status-ok")
        else:
            self._opti_status_lbl.setText(f"Deploy failed (exit {code}). See output above.")
            self._opti_status_lbl.setObjectName("status-err")
        _restyle(self._opti_status_lbl)

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
        self._scx_worker.done.connect(lambda code: self._on_scx_done(code))
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

    def _open_heroic_for_epic(self):
        cmd = heroic_epic_launcher_command()
        self._tool_log.clear()
        self._tool_log.append(f"→ {' '.join(cmd)}\n")
        self._tool_log.append("Heroic should open. Sign in to Epic Games there to install your library.")
        self._tool_log_toggle.show()
        _set_log_panel(self._tool_log_toggle, self._tool_log, False)
        self._tool_progress.hide()
        self._tool_op_status.setText("Opening Heroic Games Launcher…")
        self._tool_op_status.setObjectName("subheading")
        self._tool_op_status.show()
        _restyle(self._tool_op_status)

        try:
            subprocess.Popen(cmd)
            self._tool_op_status.setText("Heroic opened for Epic sign-in.")
            self._tool_op_status.setObjectName("status-ok")
            _restyle(self._tool_op_status)
        except Exception as exc:
            self._tool_log.append(f"\nFailed to start Heroic: {exc}")
            self._tool_op_status.setText("Failed to open Heroic.")
            self._tool_op_status.setObjectName("status-err")
            _restyle(self._tool_op_status)
            QMessageBox.warning(self, "Heroic Games Launcher", str(exc))

    def _prepare_epic_lutris_install(self) -> bool:
        prefix = os.path.expanduser("~/Games/epic-games-store")
        cache = os.path.expanduser("~/.cache/lutris/installer/epic-games-store")
        found_paths = [path for path in (prefix, cache) if os.path.exists(path)]
        if not found_paths:
            return True

        notes = []
        winetricks_log = os.path.join(prefix, "winetricks.log")
        if os.path.isfile(winetricks_log):
            try:
                with open(winetricks_log, "r", encoding="utf-8", errors="ignore") as fh:
                    if "corefonts" in fh.read():
                        notes.append("Winetricks already ran in the old Epic prefix (corefonts found).")
            except OSError:
                pass

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Reset old Epic installer state?")
        box.setText(
            "A previous Epic install attempt was found. Lutris/UMU can fail when it reuses a partial Epic prefix."
        )
        detail_lines = []
        detail_lines.extend(notes)
        detail_lines.extend([f"Found: {path}" for path in found_paths])
        detail_lines.append("")
        detail_lines.append("Choose 'Reset and Retry' to move the old state aside and reopen the installer.")
        box.setInformativeText("\n".join(detail_lines))
        reset_btn = box.addButton("Reset and Retry", QMessageBox.ButtonRole.AcceptRole)
        open_btn = box.addButton("Open Anyway", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(reset_btn)
        box.exec()

        clicked = box.clickedButton()
        if clicked == cancel_btn:
            self._tool_op_status.setText("Epic installer launch cancelled.")
            self._tool_op_status.setObjectName("subheading")
            self._tool_op_status.show()
            _restyle(self._tool_op_status)
            return False
        if clicked == open_btn:
            return True

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._tool_log.clear()
        self._tool_log.append("Preparing a clean Epic installer retry…\n")
        self._tool_log_toggle.show()
        _set_log_panel(self._tool_log_toggle, self._tool_log, False)
        for path in found_paths:
            backup = f"{path}.bak-{timestamp}"
            try:
                shutil.move(path, backup)
                self._tool_log.append(f"Moved {path} → {backup}")
            except Exception as exc:
                self._tool_log.append(f"Failed to move {path}: {exc}")
                self._tool_log_toggle.show()
                _set_log_panel(self._tool_log_toggle, self._tool_log, False)
                self._tool_op_status.setText("Epic installer reset failed.")
                self._tool_op_status.setObjectName("status-err")
                self._tool_op_status.show()
                _restyle(self._tool_op_status)
                QMessageBox.warning(
                    self,
                    "Epic installer reset",
                    f"Could not move {path}:\n{exc}"
                )
                return False

        self._tool_log.append("\nOld installer state was backed up. Relaunching Lutris…")
        self._tool_log_toggle.show()
        _set_log_panel(self._tool_log_toggle, self._tool_log, False)
        self._tool_op_status.setText("Old Epic installer state was backed up. Retrying…")
        self._tool_op_status.setObjectName("subheading")
        self._tool_op_status.show()
        _restyle(self._tool_op_status)
        return True

    def _launch_lutris_installer(self, target: str, name: str):
        if not _is_flatpak_installed("net.lutris.Lutris"):
            self._tool_op_status.setText("Lutris is not installed.")
            self._tool_op_status.setObjectName("status-err")
            self._tool_op_status.show()
            _restyle(self._tool_op_status)
            QMessageBox.warning(
                self,
                "Lutris not found",
                f"Lutris is required to install {name}.\n\nInstall it from the Gaming Tools section above."
            )
            return

        if not shutil.which("umu-run"):
            if self._tool_worker and self._tool_worker.isRunning():
                return
            self._tool_log.clear()
            self._tool_log.append("→ ujust install-umu\n")
            self._tool_log_toggle.show()
            _set_log_panel(self._tool_log_toggle, self._tool_log, False)
            self._tool_progress.show()
            self._tool_cancel_btn.setEnabled(True)
            self._tool_cancel_btn.show()
            self._tool_op_status.setText("umu-launcher not found — installing automatically…")
            self._tool_op_status.setObjectName("subheading")
            self._tool_op_status.show()
            _restyle(self._tool_op_status)
            self._tool_worker = Worker(["ujust", "install-umu"])
            self._tool_worker.line.connect(lambda ln: (
                self._tool_log.append(ln),
                self._tool_log.ensureCursorVisible(),
            ))
            self._tool_worker.done.connect(
                lambda code, t=target, n=name: self._on_umu_install_done(code, t, n)
            )
            self._tool_worker.start()
            return

        self._tool_log.clear()
        if target == "epic-games-store" and not self._prepare_epic_lutris_install():
            return

        lutris_target = target if target.startswith("lutris:") else f"lutris:install/{target}"
        cmd = lutris_installer_command(lutris_target)
        self._tool_log.append(f"→ {' '.join(cmd)}\n")
        self._tool_log.append("Lutris should open the installer dialog.")
        self._tool_log_toggle.show()
        _set_log_panel(self._tool_log_toggle, self._tool_log, False)
        self._tool_progress.hide()
        self._tool_op_status.setText(f"Opening {name} installer in Lutris…")
        self._tool_op_status.setObjectName("subheading")
        self._tool_op_status.show()
        _restyle(self._tool_op_status)

        try:
            subprocess.Popen(cmd)
            self._tool_op_status.setText(f"{name} installer opened in Lutris.")
            self._tool_op_status.setObjectName("status-ok")
            _restyle(self._tool_op_status)
        except Exception as exc:
            self._tool_log.append(f"\nFailed to start Lutris: {exc}")
            self._tool_op_status.setText(f"Failed to open {name} installer.")
            self._tool_op_status.setObjectName("status-err")
            _restyle(self._tool_op_status)
            QMessageBox.warning(self, f"{name} installer", str(exc))

    def _on_umu_install_done(self, code: int, target: str, name: str):
        self._tool_progress.hide()
        self._tool_cancel_btn.hide()
        _finish_worker(self, attr="_tool_worker")
        if code == Worker.CANCELLED:
            self._tool_op_status.setText("umu-launcher installation cancelled.")
            self._tool_op_status.setObjectName("status-warn")
            _restyle(self._tool_op_status)
            return
        if code != 0:
            self._tool_op_status.setText("umu-launcher installation failed.")
            self._tool_op_status.setObjectName("status-err")
            _restyle(self._tool_op_status)
            return
        self._tool_log.append("\numu-launcher installed. Proceeding with installer…")
        self._launch_lutris_installer(target, name)

    def _cancel_launcher_tool_operation(self):
        reply = QMessageBox.question(
            self,
            "Cancel Tool Install?",
            "Stop installing the launcher support tool? You can retry when you are ready.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        _cancel_worker(
            self,
            attr="_tool_worker",
            status_lbl=self._tool_op_status,
            log=self._tool_log,
            cancel_btn=self._tool_cancel_btn,
            message="Cancelling tool install…",
        )

    def _install_tool(self, tool: dict):
        if self._tool_worker and self._tool_worker.isRunning():
            return
        active_refs = next(r for r in self._tool_refs if r["tool"] is tool)
        self._active_tool_refs = active_refs
        for refs in self._tool_refs:
            refs["install"].setEnabled(False)
            refs["uninstall"].setEnabled(False)
        log = active_refs["log"]
        log_toggle = active_refs["log_toggle"]
        progress = active_refs["progress"]
        status_lbl = active_refs["status"]
        log.clear()
        log.append(f"→ flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo\n→ flatpak install -y flathub {tool['flatpak']}\n")
        log_toggle.show()
        _set_log_panel(log_toggle, log, False)
        progress.show()
        status_lbl.setText(f"Installing {tool['name']}…")
        status_lbl.setObjectName("subheading")
        status_lbl.show()
        _restyle(status_lbl)
        active_refs["cancel"].setEnabled(True)
        active_refs["cancel"].show()
        self._tool_worker = Worker([
            "bash", "-c",
            f"flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
            f" && flatpak install -y flathub {tool['flatpak']}",
        ])
        self._tool_worker.line.connect(lambda ln: (
            log.append(ln),
            log.ensureCursorVisible(),
        ))
        self._tool_worker.done.connect(
            lambda code, name=tool["name"]: self._on_tool_install_done(code, name)
        )
        self._tool_worker.start()

    def _on_tool_install_done(self, code: int, name: str):
        active_refs = self._active_tool_refs
        active_refs["progress"].hide()
        active_refs["cancel"].hide()
        _finish_worker(self, attr="_tool_worker")
        if code == Worker.CANCELLED:
            active_refs["status"].setText(f"{name} installation cancelled.")
            active_refs["status"].setObjectName("status-warn")
            active_refs["log"].append("\nCancelled.")
        elif code == 0:
            active_refs["status"].setText(f"{name} installed.")
            active_refs["status"].setObjectName("status-ok")
            active_refs["log"].append("\nDone.")
        else:
            active_refs["status"].setText(f"Installation failed (exit {code}).")
            active_refs["status"].setObjectName("status-err")
        _restyle(active_refs["status"])
        for refs in self._tool_refs:
            refs["install"].setEnabled(True)
            refs["uninstall"].setEnabled(True)
        self._refresh_status()

    def _cancel_tool_operation(self, refs: dict):
        if refs is not self._active_tool_refs:
            return
        reply = QMessageBox.question(
            self,
            "Cancel App Operation?",
            "Stop the running Flatpak operation? Any apps that already finished changing will keep their current state.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        _cancel_worker(
            self,
            attr="_tool_worker",
            status_lbl=refs["status"],
            log=refs["log"],
            cancel_btn=refs["cancel"],
            message="Cancelling app operation…",
        )

    def _uninstall_tool(self, tool: dict):
        if self._tool_worker and self._tool_worker.isRunning():
            return
        reply = QMessageBox.question(
            self, f"Uninstall {tool['name']}",
            f"Remove {tool['name']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        active_refs = next(r for r in self._tool_refs if r["tool"] is tool)
        self._active_tool_refs = active_refs
        for refs in self._tool_refs:
            refs["install"].setEnabled(False)
            refs["uninstall"].setEnabled(False)
        log = active_refs["log"]
        log_toggle = active_refs["log_toggle"]
        progress = active_refs["progress"]
        status_lbl = active_refs["status"]
        log.clear()
        log.append(f"→ flatpak uninstall -y {tool['flatpak']}\n")
        log_toggle.show()
        _set_log_panel(log_toggle, log, False)
        progress.show()
        status_lbl.setText(f"Uninstalling {tool['name']}…")
        status_lbl.setObjectName("subheading")
        status_lbl.show()
        _restyle(status_lbl)
        active_refs["cancel"].setEnabled(True)
        active_refs["cancel"].show()
        self._tool_worker = Worker(
            ["flatpak", "uninstall", "-y", tool["flatpak"]]
        )
        self._tool_worker.line.connect(lambda ln: (
            log.append(ln),
            log.ensureCursorVisible(),
        ))
        self._tool_worker.done.connect(
            lambda code, name=tool["name"]: self._on_tool_uninstall_done(code, name)
        )
        self._tool_worker.start()

    def _on_tool_uninstall_done(self, code: int, name: str):
        active_refs = self._active_tool_refs
        active_refs["progress"].hide()
        active_refs["cancel"].hide()
        _finish_worker(self, attr="_tool_worker")
        if code == Worker.CANCELLED:
            active_refs["status"].setText(f"{name} uninstall cancelled.")
            active_refs["status"].setObjectName("status-warn")
            active_refs["log"].append("\nCancelled.")
        elif code == 0:
            active_refs["status"].setText(f"{name} uninstalled.")
            active_refs["status"].setObjectName("status-ok")
            active_refs["log"].append("\nDone.")
        else:
            active_refs["status"].setText(f"Uninstall failed (exit {code}).")
            active_refs["status"].setObjectName("status-err")
        _restyle(active_refs["status"])
        for refs in self._tool_refs:
            refs["install"].setEnabled(True)
            refs["uninstall"].setEnabled(True)
        self._refresh_status()

    def _update_proton_cachyos(self):
        if self._pc_worker and self._pc_worker.isRunning():
            return
        self._pc_update_btn.setEnabled(False)
        self._pc_log.clear()
        self._pc_log.append("→ /usr/bin/kyth-proton-cachyos-update\n")
        self._pc_log_toggle.show()
        _set_log_panel(self._pc_log_toggle, self._pc_log, False)
        self._pc_progress.show()
        self._pc_op_status.setText("Checking for Proton-CachyOS update…")
        self._pc_op_status.setObjectName("subheading")
        self._pc_op_status.show()
        _restyle(self._pc_op_status)
        self._pc_worker = Worker(["/usr/bin/kyth-proton-cachyos-update"])
        self._pc_worker.line.connect(lambda ln: (
            self._pc_log.append(ln),
            self._pc_log.ensureCursorVisible(),
        ))
        self._pc_worker.done.connect(self._on_pc_update_done)
        self._pc_worker.start()

    def _on_pc_update_done(self, code: int):
        self._pc_progress.hide()
        _finish_worker(self, attr="_pc_worker")
        self._pc_update_btn.setEnabled(True)
        if code == 0:
            self._pc_op_status.setText("Proton-CachyOS is up to date.")
            self._pc_op_status.setObjectName("status-ok")
            self._pc_log.append("\nDone.")
        else:
            self._pc_op_status.setText(f"Update failed (exit {code}).")
            self._pc_op_status.setObjectName("status-err")
        _restyle(self._pc_op_status)
        self._refresh_status()
