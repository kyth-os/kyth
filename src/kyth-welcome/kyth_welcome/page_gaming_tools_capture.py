import shutil
from pathlib import Path

# __KYTH_GENERATED_IMPORTS__
from .core_base import restyle
from .services.gaming import opticscaler_deploy_command
from .services.launch import popen
from .actions import _install_flatpak_inline
from .services.runtime import Worker, guard_disposed, finish_worker, guard_disposed
from .qt import (
    QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTextEdit, QVBoxLayout, Qt, single_shot,
)
from .widgets import ActionRow, CommandResultPanel, _copy_text, _make_card, _make_tip_card


class _CaptureToolsMixin:
    """GPU/capture tuning helpers: LACT/CoreCtrl/OBS, OptiScaler, and streaming/Discord readiness."""

    def _build_capture_tools_card(self):
        # LACT and OBS install inline: their buttons disable/relabel
        # themselves while running, so they need a live reference to
        # themselves — connected below instead of passed as callbacks.
        card, (lact_btn, _corectrl_btn, obs_btn) = _make_tip_card(
            "Advanced GPU and Capture Tools",
            "LACT and CoreCtrl cover AMD GPU tuning, while OBS uses the built-in "
            "obs-vkcapture and v4l2loopback support for game capture and virtual camera workflows.",
            primary=None,
            buttons=[
                ("Install LACT", None),
                ("Open CoreCtrl", lambda _=False: self._open_corectrl()),
                ("Install OBS", None),
            ],
        )
        lact_btn.clicked.connect(lambda _=False, b=lact_btn: _install_flatpak_inline(
            self, b, "io.github.ilya_zlobintsev.LACT", "LACT"))
        obs_btn.clicked.connect(lambda _=False, b=obs_btn: self._install_obs_inline(b))
        self._add(card)

    def _build_opticscaler_card(self):
        opti_card, opti_layout = _make_card()
        opti_title = QLabel("OptiScaler — Universal Upscaling")
        opti_title.setObjectName("card-title")
        opti_layout.addWidget(opti_title)
        opti_desc = QLabel(
            "Enables FSR2/3/4, XeSS, and DLSS-translation in DirectX 11/12 games, "
            "including titles that ship without upscaling. On Proton-CachyOS or "
            "GE-Proton 11, prefer the built-in hook: "
            "<code>PROTON_USE_OPTISCALER=1 %command%</code>. "
            "Manual folder deploy plus "
            "<code>WINEDLLOVERRIDES=\"nvngx=n,b\" %command%</code> "
            "is the fallback for Valve Proton."
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
        opti_copy_btn.setToolTip("Copies: PROTON_USE_OPTISCALER=1 %command%")
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

    def _build_streaming_readiness_card(self):
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
        self._add(streaming_card)

    def _build_discord_fix_card(self):
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
        discord_fix_layout.addSpacing(8)
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

    def _open_corectrl(self):
        if shutil.which("corectrl"):
            popen(["corectrl"])
            return
        QMessageBox.information(
            self,
            "CoreCtrl",
            "CoreCtrl is not installed in this image. Use LACT for AMD GPU tuning, or rebuild with CoreCtrl available in the package repos.",
        )

    def _copy_opticscaler_launch_opt(self, btn: QPushButton):
        _copy_text("PROTON_USE_OPTISCALER=1 %command%")
        btn.setText("Copied!")
        single_shot(btn, 2000, lambda: btn.setText("Copy Launch Option"))

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
        restyle(self._opti_status_lbl)
        cmd = opticscaler_deploy_command(game_dir)
        self._opticscaler_worker = Worker(cmd)
        self._opticscaler_worker.line.connect(guard_disposed(lambda ln: (
            self._opti_log.append(ln),
            self._opti_log.ensureCursorVisible(),
        )))
        self._opticscaler_worker.done.connect(guard_disposed(lambda code: self._on_opticscaler_done(code, btn)))
        self._opticscaler_worker.start()

    def _on_opticscaler_done(self, code: int, btn: QPushButton):
        btn.setEnabled(True)
        finish_worker(self, attr="_opticscaler_worker")
        if code == 0:
            self._opti_status_lbl.setText(
                "Deployed. Set Steam launch option: WINEDLLOVERRIDES=\"nvngx=n,b\" %command%"
            )
            self._opti_status_lbl.setObjectName("status-ok")
        else:
            self._opti_status_lbl.setText(f"Deploy failed (exit {code}). See output above.")
            self._opti_status_lbl.setObjectName("status-err")
        restyle(self._opti_status_lbl)