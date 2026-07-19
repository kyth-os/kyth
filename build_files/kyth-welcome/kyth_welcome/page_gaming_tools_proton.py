# __KYTH_GENERATED_IMPORTS__
from .core_base import _restyle
from .services.launch import flatpak_run
from .services.software import Worker, _finish_worker, _install_flatpak_inline, _is_flatpak_installed
from .qt import QDesktopServices, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit, QUrl, Qt
from .widgets import _copy_text, _launch_opt_label, _launch_opt_value, _make_card, _set_log_panel


class _ProtonToolsMixin:
    """Proton-CachyOS updates, optional GE-Proton, vkBasalt, and the combos reference."""

    def _build_proton_cachyos_card(self):
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

    def _build_ge_proton_card(self):
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

    def _build_vkbasalt_card(self):
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

    def _build_combos_reference(self):
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

    def _open_protonupqt(self):
        if _is_flatpak_installed("net.davidotek.pupgui2"):
            flatpak_run("net.davidotek.pupgui2")
            return
        btn = self.sender()
        if not isinstance(btn, QPushButton):
            btn = QPushButton()

        def _launch_when_done(code: int):
            if code == 0:
                flatpak_run("net.davidotek.pupgui2")

        _install_flatpak_inline(
            self, btn, "net.davidotek.pupgui2", "ProtonUp-Qt", done_cb=_launch_when_done,
        )

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
